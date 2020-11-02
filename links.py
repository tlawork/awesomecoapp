import os
import json
import glob
import re

from flask import Flask, request
from waitress import serve
from flask_cors import CORS

indexhtml = """<h1 style="color: #5e9ca0;">AMAZING COMPANY</h1>
<h2 style="color: #2e6c80;">API DEFINITION:&nbsp; url/v197tradeshift/xxxx</h2>
<p>&nbsp;</p>
<ul style="list-style-position: initial; list-style-image: initial; font-size: 14px; line-height: 32px; font-weight: bold;">
<li style="clear: both;">/v197tradeshift/reset - GET - Reset Database to Sample Data</li>
<li style="clear: both;">/v197tradeshift/add/&lt;node&gt;/&lt;ID&gt; - POST - Adds new item with ID and attaches to node parent.</li>
<li style="clear: both;">/v197tradeshift/move/&lt;dest&gt;/&lt;node&gt; - PUT - move node to destination</li>
<li style="clear: both;">/v197tradeshift/&lt;node&gt; - GET - Gets the tree from this node.</li>
<li style="clear: both;">/v197tradeshift/details/&lt;node&gt; - GET - Gets just node details</li>
</ul>
<p>&nbsp;</p>
<p>Todd Lindstrom<br />Applicant to Tradeshift.</p>
"""

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
            raise APIException(f"could not find destination id {destid}", 400)
        child = self.findby_id(fromid)
        if not child:
            raise APIException(f"could not find source id {fromid}", 400)

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

def sample_treedata():
    treedata = TreeClass("/home/ubuntu/tradeshift/treedata")
    treedata.set_head(Node("ROOT"))
    treedata.add(treedata.head, Node("A"))
    BNODE = treedata.add(treedata.head, Node("B"))
    treedata.add(treedata.head, Node("C"))
    treedata.add(BNODE, Node("D"))
    EEE = treedata.add(BNODE, Node("E"))
    treedata.add(EEE, Node("F F"))
    treedata.add(EEE, Node("G G"))
    return treedata

mypath = "/home/ubuntu/tradeshift/treepy/treedata"
mytree = None

def import_if_backup_data_exists():
    global mytree
    if not glob.glob(f"{mypath}/*.json"):
        # there are no backups, so populate with sample data
        mytree = sample_treedata()
    else:
        mytree = TreeClass(mypath)
        mytree.import_tree()

# def sample_unit_test():
#     """ sample unit test that goes with sample data above """
#     treedata = sample_treedata()
#     print("------------------ BEFORE -----------------------")
#     treedata.tprint(treedata.head)
#     treedata.move_by_id("C", "B")    # B move to C
#     print("------------------ AFTER -----------------------")
#     treedata.tprint(treedata.head)

# #################### WEB STUFF NOW ###################
#
# Routes IP:  ec2......com:5000/v197tradeshift/reset = start over to sample data
#                              /v197tradeshift/add

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})

def success_reply(code=200, message="ok"):
    rv = {'status_code': code, 'message': message}
    return json.dumps(rv)

@app.route('/', methods=['GET'])
def hello_world():
    return indexhtml

@app.route('/v197tradeshift/reset', methods=['GET'])
def reset_database():
    global mytree
    mytree.destroy()
    mytree = None
    mytree = sample_treedata()
    return mytree.dump_all()

@app.errorhandler(404)
def four_o_four(e):
    """ an HTTP error for those using a browser for GET """
    return """<h1><span style="color: #ff0000;">
    <strong>SORRY THAT IS NOT A VALID ACCESS</strong>
    </span></h1>""" + indexhtml

@app.errorhandler(APIException)
def handle_api_exception(error):
    response = json.dumps(error.to_dict())
    return response

@app.route('/v197tradeshift/debug', methods=['GET'])
def webdebug():
    """ HTTP Debug Only """
    global mytree
    return mytree.webprint()


def is_string_ok(s):
    """ return boolean true if no special characters """
    regex = re.compile(r'[@_!#$%^&*()<>?/\|}{~:]')
    if (regex.search(s)):
        raise APIException("Illegal characters in input.")


@app.route('/v197tradeshift/add/<s_node>/<s_id>', methods=['GET', 'POST'])
def add_node(s_node, s_id):
    global mytree
    # input sanity
    is_string_ok(s_node)
    is_string_ok(s_id)
    if request.method == 'GET':
        raise APIException("/v197tradeshift/add... does not allow GET. Please use POST.", 405)
    if mytree.key_exists(s_id):
        raise APIException(f"{s_id} already exists.")
    parent = mytree.findby_id(s_node)
    if parent is None:
        raise APIException(f"{s_node} is not a valid parent node.")
    newnode = Node(s_id)
    mytree.add(parent, newnode)
    return success_reply()

@app.route('/v197tradeshift/<nodeid>', methods=['GET'])
def mainget(nodeid):
    global mytree
    is_string_ok(nodeid)
    node = mytree.findby_id(nodeid)
    if node is None:
        raise APIException(f"{nodeid} does not exist")
    rv = mytree.dump_from(nodeid)
    return rv


@app.route('/v197tradeshift/details/<nodeid>', methods=['GET'])
def getdetails(nodeid):
    global mytree
    is_string_ok(nodeid)
    node = mytree.findby_id(nodeid)
    if node is None:
        raise APIException(f"{nodeid} does not exist")
    rd = node.to_dict()
    print(repr(rd))
    rd['root'] = "ROOT"   # this is a constant but a requirement
    rd['status_code'] = 200
    rd['message'] = 'OK'
    rv = json.dumps(rd, indent=2)
    return rv

@app.route('/v197tradeshift/move/<destid>/<nodeid>')
def moveto(destid, nodeid):
    """ move the node to reparent to dest """
    global mytree
    is_string_ok(destid)
    is_string_ok(nodeid)
    mytree.move_by_id(destid, nodeid)
    # not specified in spec but will return the new data for destination
    rv = getdetails(destid)
    rv.replace('"OK"', f"Node {nodeid} reparented to {destid}")
    return rv


if __name__ == '__main__':

    import_if_backup_data_exists()

    # # production
    serve(app, port=5000)

    # DEBUG
    # app.run(host='0.0.0.0', debug=True, port=5000)

    # future unit test
    # mytree.move_by_id("C", "B")  # B moves under C
    # print("-------AFTER---------")
    # mytree.tprint(mytree.head)
