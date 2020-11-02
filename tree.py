import os
import sys
import json
import glob
import re

class Node:
    def __init__(self, id=None):
        self.id = id
        self.children = []
        self.parent = None
        self.height = -1

    def to_dict(self):
        d = {}
        d['id'] = self.id
        if self.parent:
            d['parent-id'] = self.parent.id
        else:
            d['parent-id'] = "none"
        d['height'] = self.height
        return d


class APIException(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        rv['status_code'] = self.status_code
        return rv

class TreeClass:

    def __init__(self, data_location):
        self.head = None
        self.quick = {}
        self.data_location = data_location

    def import_tree(self):
        """ import from disk - start from ROOT.json """
        for path in glob.glob(self.data_location + "/*.json"):
            id = os.path.basename(path).replace(".json", "")
            print(f"IMPORTING {id}")
            newnode = Node(id)
            self.quick[id] = newnode
            data = {}
            with open(path, "r") as rfs:
                data = json.load(rfs)
            newnode.height = data['height']
            newnode.childlabels = data['children']
            newnode.parentlabel = data['parent']
            if id == "ROOT":
                self.head = newnode
        # at this point quick has all elements we just
        # need to set parent and children links from labels

        for k in self.quick.keys():
            node = self.quick[k]
            node.parent = self.findby_id(node.parentlabel)
            for label in node.childlabels:
                node.children.append(self.findby_id(label))
            self.print(node)

    def key_exists(self, id):
        """ does a key exist or not """
        return id in self.quick.keys()

    def write_data_backup(self, node):
        """ writes object in json format with class objects by ID - then on import
            the id will change to a node format. This achieves persistance without
            the need for a database. """
        filename = f"{self.data_location}/{node.id}.json"
        jback = {
            "id": node.id,
            "children": [],
            "parent": node.parent.id if node.parent else "none",
            "height": node.height
        }
        for child in node.children:
            jback['children'].append(child.id)
        with open(filename, 'w') as fp:
            json.dump(jback, fp)

    def set_head(self, node):
        self.head = node
        self.head.height = 0
        self.quick[node.id] = node
        self.write_data_backup(node)

    def get_head(self):
        """ getter for head - but .head is visible too """
        return self.head

    def print(self, node):
        parentid = "None" if not node.parent else node.parent.id
        print(f"ID:{node.id}, childCount={len(node.children)}, Height={node.height}, ParentID={parentid}")

    def tprint(self, fromwhere):
        """ debug console print """
        self.print(fromwhere)
        for child in fromwhere.children:
            self.tprint(child)  # recursive

    def webprint(self):
        """ debug web api to see layer by layer up to max 10 layers """
        rv = ""
        for layer in range(10):
            out = f"{layer}: "
            count = 0
            for k in self.quick.keys():
                node = self.quick[k]
                if node.height == layer:
                    count = count + 1
                    out = out + node.id + ":"
            rv += out + "<br>"
            if count == 0:
                break
        return rv

    def findby_id(self, id):
        """ given an id - find the class object """
        rv = None
        if id in self.quick.keys():
            rv = self.quick[id]
        return rv

    def add(self, parent, child):
        """ add routine - these are nodes not ids """
        print(f"Attaching {child.id} to {parent.id}")
        child.parent = parent
        child.height = parent.height + 1
        # this is a raw add not a move - so no propogation of child heights needed
        if child in parent.children:
            raise APIException("Child already added to this parent", 409)
        parent.children.append(child)
        self.quick[child.id] = child
        self.write_data_backup(child)
        self.write_data_backup(child.parent)
        return child

    def dump_all(self):
        return self.dump_from(self.head.id)

    def dump_from(self, id):
        start = None
        if id in self.quick.keys():
            start = self.quick[id]
        if not start:
            raise APIException(f"No such starting id {id}")
        st = self._recursive_dump(start)
        return '{"status_code":200, "message":"ok", "response": [' + st + ']}'

    def _recursive_dump(self, node):
        d = node.to_dict()
        d['root'] = self.head.id  # known data added to every item per requirements
        json_string = json.dumps(d, indent=2)
        for child in node.children:
            json_string = json_string + "," + self._recursive_dump(child)
        return json_string

    def _recursive_set_height(self, node):
        node.height = node.parent.height + 1
        self.write_data_backup(node)
        for kids in node.children:
            self._recursive_set_height(kids)

    def isdescendant(self, dest, child):
        """ go through all the child nodes searching for dest.
            if found return true """
        rv = False
        if dest in child.children:
            return True
        for kid in child.children:
            rv = self.isdescendant(dest, kid)
        return rv

    def move_by_id(self, destid, fromid):
        """ move a node to a new parent indexed by id
            destid <===== fromid
            this is a critical section and must be done atomically
            another critical note: you cant move a node to a sub child of the same node
        """

        dest = self.findby_id(destid)
        if not dest:
            raise APIException(f"Could not find destination id {destid}", 400)
        child = self.findby_id(fromid)
        if not child:
            raise APIException(f"Could not find source id {fromid}", 400)

        # final check - we cant move a parent to a node in its own tree
        # so we have to scan (recursively) to see if destination is a
        # remote child of child.

        if (self.isdescendant(dest, child)):
            raise APIException("You can not move a node deeper in its own tree", 400)

        # to move a node we must
        #   1. go to the child.parent and remove child from the children list
        #   2. modify the parent to the new parent
        #   3. find the level of the parent and set child new level - then send that downstream.

        # BEGIN CRITICAL SECTION - no reads should be allowed during this operation
        child.parent.children.remove(child)
        self.write_data_backup(child.parent)  # backs up the former (original) parent to disk
        dest.children.append(child)
        child.parent = dest
        child.height = child.parent.height + 1
        self.write_data_backup(child)
        for kids in child.children:
            self._recursive_set_height(kids)
        self.write_data_backup(child.parent)  # finally backs up the new parent
        # END CRITICAL SECTION

    def destroy(self):
        """ Not 100% sure this is necessary, not knowing the details of
            every python installation - this just sets some class pointers
            to none to make sure memory is cleaned up. """
        try:
            for file in glob.glob(self.data_location + "/*.json"):
                os.remove(file)
            for k in self.quick.keys():
                node = self.quick[k]
                node.parent = None
                node.children = None
            self.quick = None
        except Exception:
            pass  # if nothing is there dont worry
