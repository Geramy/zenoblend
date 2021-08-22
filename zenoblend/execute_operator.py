import bpy


class ZenoApplyOperator(bpy.types.Operator):
    """Apply the Zeno graph"""
    bl_idname = "node.zeno_apply"
    bl_label = "Apply"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ZenoNodeTree'

    def execute(self, context):
        from . import scenario
        data = dump_scene()
        scenario.load_scene(data)
        scenario.frame_update_callback()
        return {'FINISHED'}


class ZenoStopOperator(bpy.types.Operator):
    """Stop the running Zeno graph"""
    bl_idname = "node.zeno_stop"
    bl_label = "Stop"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ZenoNodeTree'

    def execute(self, context):
        from . import scenario
        scenario.delete_scene()
        return {'FINISHED'}


class ZenoReloadOperator(bpy.types.Operator):
    """Reload Zeno graphs"""
    bl_idname = "node.zeno_reload"
    bl_label = "Reload"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ZenoNodeTree'

    def execute(self, context):
        from .node_system import init_node_subgraphs, deinit_node_subgraphs
        deinit_node_subgraphs()
        init_node_subgraphs()
        reinit_subgraph_sockets()
        return {'FINISHED'}


def draw_menu(self, context):
    if context.area.ui_type == 'ZenoNodeTree':
        self.layout.separator()
        self.layout.operator("node.zeno_apply", text="Apply Graph")
        self.layout.operator("node.zeno_stop", text="Stop Running Graph")
        self.layout.operator("node.zeno_reload", text="Reload Graph Nodes")


classes = (
    ZenoApplyOperator,
    ZenoStopOperator,
    ZenoReloadOperator,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.NODE_MT_context_menu.append(draw_menu)


def unregister():
    bpy.types.NODE_MT_context_menu.remove(draw_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


def reinit_subgraph_sockets():
    for tree_name, tree in bpy.data.node_groups.items():
        if tree.bl_idname != 'ZenoNodeTree': continue
        for node_name, node in tree.nodes.items():
            if not hasattr(node, 'zeno_type'): continue
            node.reinit()


def load_from_zsg(prog):
    graphs = prog['graph']
    for key, val in graphs.items():
        if key in bpy.data.node_groups:
            del bpy.data.node_groups[key]
        tree = bpy.data.node_groups.new(key, 'ZenoNodeTree')
        nodes = val['nodes']

        nodesLut = {}
        for ident, data in nodes.items():
            type = data['name']
            if type in graphs:
                type = 'Subgraph'
            node = tree.nodes.new('ZenoNode_' + type)
            nodesLut[ident] = node

        for ident, data in nodes.items():
            for key, connection in data['inputs'].items():
                try:
                    srcNode, srcSock, deflVal = connection
                except ValueError:
                    print('ValueError:', key, connection)
                    continue
                if deflVal is not None:
                    node.inputs[key].default_value = deflVal
                if srcNode is None:
                    continue
                if key not in node.inputs:
                    node.inputs.new('ZenoNodeSocket', key)
                if srcNode not in nodesLut:
                    print('nodesLut KeyError:', srcNode)
                    continue
                srcNode = nodesLut[srcNode]
                if srcNode not in srcNode.outputs:
                    srcNode.outputs.new('ZenoNodeSocket', key)
                tree.links.new(node.inputs[key], srcNode.outputs[srcSock])

            for key, value in data['params'].items():
                if key not in node.inputs:
                    print('KeyError:', key)
                    continue
                key = key + ':'
                node.inputs[key].default_value = value

bpy.load_zsg = lambda path: load_from_zsg(__import__('json').load(open(path)))


def find_tree_sub_category(tree):
    assert tree.bl_idname == 'ZenoNodeTree', tree
    if 'SubCategory' in tree.nodes:
        node = tree.nodes['SubCategory']
        if node.zeno_type == 'SubCategory':
            return node.inputs['name:'].default_value
    for node_name, node in tree.nodes.items():
        if not hasattr(node, 'zeno_type'): continue
        if node.zeno_type == 'SubCategory':
            return node.inputs['name:'].default_value
    return 'uncategorized'


def find_tree_sub_io_names(tree):
    assert tree.bl_idname == 'ZenoNodeTree', tree
    inputs = []
    outputs = []
    for node_name, node in tree.nodes.items():
        if not hasattr(node, 'zeno_type'): continue
        if node.zeno_type == 'SubInput':
            type = node.inputs['type:'].default_value
            name = node.inputs['name:'].default_value
            defl = node.inputs['defl:'].default_value
            inputs.append((type, name, defl))
        elif node.zeno_type == 'SubOutput':
            type = node.inputs['type:'].default_value
            name = node.inputs['name:'].default_value
            defl = node.inputs['defl:'].default_value
            outputs.append((type, name, defl))
    return inputs, outputs


def dump_tree(tree):
    assert tree.bl_idname == 'ZenoNodeTree', tree
    for node_name, node in tree.nodes.items():
        if not hasattr(node, 'zeno_type'): continue
        node_type = node.zeno_type
        yield ('addNode', node_type, node_name)
        for input_name, input in node.inputs.items():
            if input.is_linked:
                assert len(input.links) == 1
                link = input.links[0]
                src_node_name = link.from_node.name
                src_socket_name = link.from_socket.name
                yield ('bindNodeInput', node_name, input_name,
                        src_node_name, src_socket_name)
            elif hasattr(input, 'default_value'):
                value = input.default_value
                yield ('setNodeInput', node_name, input_name, value)
        if node.zeno_type == 'Subgraph':
            yield ('setNodeInput', node_name, 'name:', node.graph_name)
        yield ('completeNode', node_name)


def dump_all_trees():
    yield ('clearAllState',)
    for name, tree in bpy.data.node_groups.items():
        if tree.bl_idname != 'ZenoNodeTree': continue
        yield ('switchGraph', name)
        yield from dump_tree(tree)


def dump_scene():
    import json
    data = list(dump_all_trees())
    data = json.dumps(data)
    return data
