# List of valid osd flags
OSD_FLAGS = [
    'pause', 'noup', 'nodown', 'noout', 'noin', 'nobackfill',
    'norecover', 'noscrub', 'nodeep-scrub',
]

# Implemented osd commands
OSD_IMPLEMENTED_COMMANDS = ['scrub', 'deep_scrub', 'repair']

# Valid values for the 'var' argument to 'ceph osd pool set'
POOL_PROPERTIES = [
    'size', 'min_size', 'crash_replay_interval', 'pg_num',
    'pgp_num', 'crush_ruleset', 'hashpspool',
]

# Valid values for the 'ceph osd pool set-quota' command
POOL_QUOTA_PROPERTIES = [
    ('quota_max_bytes', 'max_bytes'),
    ('quota_max_objects', 'max_objects'),
]

# Transform command to a human readable form
def HUMANIFY(command):
    out = [command['prefix']]

    for arg, val in command.iteritems():
        if arg != 'prefix':
            out.append("%s=%s" % (str(arg), str(val)))

    return " ".join(out)


def INVALID_POOL_ARGS(args):
    POOL_ARGS = POOL_PROPERTIES + map(
        lambda x: x[0],
        POOL_QUOTA_PROPERTIES
    )

    invalid = []
    for arg in args:
        if arg not in POOL_ARGS:
            invalid.append(arg)

    return invalid


# TODO: fix this to handle pg/pgp_num better, etc
def POOL_UPDATE_COMMANDS(pool_name, args):
    commands = []
    # Run the pool setting properties in parallel
    for var in POOL_PROPERTIES:
        if var in args:
            commands.append({
                'prefix': 'osd pool set',
                'pool': pool_name,
                'var': var,
                'val': args[var],
            })

    for (var, field) in POOL_QUOTA_PROPERTIES:
        if var in args:
            commands.append({
                'prefix': 'osd pool set-quota',
                'pool': pool_name,
                'field': field,
                'val': str(args[var]),
            })

    return [commands]


def CRUSH_RULE_OSDS(nodes, rule):
    nodes_by_id = dict((n['id'], n) for n in nodes)

    def _gather_leaf_ids(node):
        if node['id'] >= 0:
            return set([node['id']])

        result = set()
        for child_id in node['children']:
            if child_id >= 0:
                result.add(child_id)
            else:
                result |= _gather_leaf_ids(nodes_by_id[child_id])

        return result

    def _gather_descendent_ids(node, typ):
        result = set()
        for child_id in node['children']:
            child_node = nodes_by_id[child_id]
            if child_node['type'] == typ:
                result.add(child_node['id'])
            elif 'children' in child_node:
                result |= _gather_descendent_ids(child_node, typ)

        return result

    def _gather_osds(root, steps):
        if root['id'] >= 0:
            return set([root['id']])

        osds = set()
        step = steps[0]
        if step['op'] == 'choose_firstn':
            # Choose all descendents of the current node of type 'type'
            d = _gather_descendent_ids(root, step['type'])
            for desc_node in [nodes_by_id[i] for i in d]:
                osds |= _gather_osds(desc_node, steps[1:])
        elif step['op'] == 'chooseleaf_firstn':
            # Choose all descendents of the current node of type 'type',
            # and select all leaves beneath those
            for desc_node in [nodes_by_id[i] for i in _gather_descendent_ids(root, step['type'])]:
                # Short circuit another iteration to find the emit
                # and assume anything we've done a chooseleaf on
                # is going to be part of the selected set of osds
                osds |= _gather_leaf_ids(desc_node)
        elif step['op'] == 'emit':
            if root['id'] >= 0:
                osds |= root['id']

        return osds

    osds = set()
    for i, step in enumerate(rule['steps']):
        if step['op'] == 'take':
            osds |= _gather_osds(nodes_by_id[step['item']], rule['steps'][i + 1:])
    return osds
