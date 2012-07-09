from bulbs.model import Node, Relationship
from bulbs.property import String
from bulbs.neo4jserver import Graph, Config

# Used to capture neo4j connection exceptions
import httplib2

import config as vlconf
from bl.vl.kb.drivers.omero.utils import ome_hash


class OME_Object(Node):
    element_type = 'ome_object'
    
    obj_class = String(nullable=False)
    obj_id = String(nullable=False)
    obj_hash = String(nullable=False)

    def __hash__(self):
        return self.eid


class OME_Action(Relationship):
    label = 'produces'
    act_type = String(nullable=False)
    act_id = String(nullable=False)
    act_hash = String(nullable=False)

    def __hash__(self):
        return self.eid


class DependencyTreeError(Exception):
    pass
    

class DependencyTree(object):

    DIRECTION_INCOMING = 1
    DIRECTION_OUTGOING = 2
    DIRECTION_BOTH     = 3

    def __init__(self, kb):
        self.kb = kb
        gconf = Config(vlconf.NEO4J_URI)
        try:
            self.graph = Graph(gconf)
        except httplib2.ServerNotFoundError:
            raise DependencyTreeError('Unable to find Node4J server at %s' % 
                                      vlconf.NEO4J_URI)
        except httplib2.socket.error:
            raise DependencyTreeError('Connection refused by Node4J server')
        self.graph.add_proxy('ome_objects', OME_Object)
        self.graph.add_proxy('produces', OME_Action)
        if not self.do_consistency_check():
            raise DependencyTreeError('Graph out-of-sync!')


    # TODO: do a consistency check against OMERO in order to check that
    # everything inside the Graph is in sync
    def do_consistency_check(self):
        return True

    def dump_node(self, obj):
        self._save_node({'obj_class' : type(obj).__name__,
                         'obj_id' : obj.id,
                         'obj_hash' : ome_hash(obj.ome_obj)})

    def dump_edge(self, source, dest, act):
        self._save_edge({'act_type' : type(act).__name__,
                         'act_id' : act.id,
                         'act_hash' : ome_hash(act.ome_obj)},
                        ome_hash(source.ome_obj),
                        ome_hash(dest.ome_obj))

    def _save_node(self, node_conf):
        self.graph.ome_objects.get_or_create('obj_hash', node_conf['obj_hash'],
                                             node_conf)

    def _save_edge(self, edge_conf, src_hash, dest_hash):
        edges = list(self.graph.produces.index.lookup(act_hash = edge_conf['act_hash']))
        if len(edges) == 1:
            return
        elif len(edges) == 0:
            src_node = self.__get_node_by_hash(src_hash)
            if not src_node:
                raise DependencyTreeError('Unmapped source node, unable to create the edge')
            dest_node = self.__get_node_by_hash(dest_hash)
            if not dest_node:
                raise DependencyTreeError('Unmapped destinantion node, unable to create the edge')
            self.graph.produces.create(src_node, dest_node, **edge_conf)
        else:
            raise DependencyTreeError('Multiple edges with act_hash %s' % edge_conf['act_hash'])

    def __get_node(self, obj):
        return self.__get_node_by_hash(ome_hash(obj.ome_obj))

    def __get_node_by_hash(self, node_hash):
        nodes = list(self.graph.ome_objects.index.lookup(obj_hash = node_hash))
        if len(nodes) == 1:
            return nodes[0]
        elif len(nodes) == 0:
            return None
        else:
            raise DependencyTreeError('Multiple nodes with obj_hash = %s' % ome_hash(obj))

    def __get_ome_obj(self, node):
        try:
            return self.kb._CACHE(node.obj_hash)
        except KeyError, ke:
            return self.kb.get_by_vid(getattr(self.kb, node.obj_class),
                                      str(node.obj_id))

    def __get_ome_action(self, edge):
        try:
            return self.kb._CACHE(edge.act_hash)
        except KeyError, ke:
            return self.kb.get_by_vid(edge.act_class, edge.act_hash)

    def __get_connected_nodes(self, node, direction, depth,
                              visited_nodes = None):
        if not visited_nodes:
            visited_nodes = set()
        if direction not in (self.DIRECTION_INCOMING,
                             self.DIRECTION_OUTGOING,
                             self.DIRECTION_BOTH):
            raise DependencyTreeError('Not a valid direction for graph traversal')
        if depth == 0:
            visited_nodes.add(node)
            return visited_nodes
        if direction == self.DIRECTION_INCOMING:
            connected = list(node.inV('produces'))
        elif direction == self.DIRECTION_OUTGOING:
            connected = list(node.outV('produces'))
        elif direction == self.DIRECTION_BOTH:
            connected = list(node.bothV('produces'))
        visited_nodes.add(node)
        connected = set(connected) - visited_nodes
        if len(connected) == 0:
            return visited_nodes
        else:
            if not depth is None:
                depth = depth - 1
            return set.union(*[self.__get_connected_nodes(cn, direction, depth, visited_nodes)
                               for cn in connected])

    def get_connected(self, ome_obj, aklass=None,
                      direction = DIRECTION_BOTH, query_depth = None):
        obj_node = self.__get_node(ome_obj)
        if not obj_node:
            raise DependencyTreeError('Unable to lookup object %s:%s into the graph' % 
                                      (type(ome_obj).__name__, ome_obj.id))
        try:
            connected_nodes = self.__get_connected_nodes(obj_node, direction, query_depth)
        except RuntimeError, re:
            raise DependencyTreeError(re) 
        # Remove the first node, we don't need it
        connected_nodes.remove(obj_node)
        if aklass:
            return [self.__get_ome_obj(cn) for cn in connected_nodes
                    if cn.obj_class == aklass]
        else:
            return [self.__get_ome_obj(cn) for cn in connected_nodes]
