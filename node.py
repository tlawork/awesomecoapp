


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
