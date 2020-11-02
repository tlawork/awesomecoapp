import os
import json
import glob
import re

from flask import Flask, request
from waitress import serve
from flask_cors import CORS

from tree import APIException, TreeClass, Node

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

mypath = os.getcwd() + "/treedata"
mytree = None

def sample_treedata():
    treedata = TreeClass(mypath)
    treedata.set_head(Node("ROOT"))
    treedata.add(treedata.head, Node("A"))
    BNODE = treedata.add(treedata.head, Node("B"))
    treedata.add(treedata.head, Node("C"))
    treedata.add(BNODE, Node("D"))
    EEE = treedata.add(BNODE, Node("E"))
    treedata.add(EEE, Node("F F"))
    treedata.add(EEE, Node("G G"))
    return treedata


# putting the raw data at common location - will change for dockerized

def import_if_backup_data_exists():
    global mytree
    print(f"Getting data from {mypath}")
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
        raise APIException(f"Node {nodeid} does not exist")
    rv = mytree.dump_from(nodeid)
    return rv


@app.route('/v197tradeshift/details/<nodeid>', methods=['GET'])
def getdetails(nodeid):
    global mytree
    is_string_ok(nodeid)
    node = mytree.findby_id(nodeid)
    if node is None:
        raise APIException(f"Node {nodeid} does not exist")
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
