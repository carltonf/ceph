from flask import request
from flask_restful import Resource

import json
import traceback

from common import *
from functools import wraps

## We need this to access the instance of the module
#
# We can't use 'from module import instance' because
# the instance is not ready, yet (would be None)
import module


# Helper function to catch and log the exceptions
def catch(f):
    @wraps(f)
    def catcher(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            module.instance.log.error(str(traceback.format_exc()))
            return {'error': str(traceback.format_exc()).split('\n')}
    return catcher


# Helper function to lock the function
def lock(f):
    @wraps(f)
    def locker(*args, **kwargs):
        with module.instance.requests_lock:
            return f(*args, **kwargs)
    return locker



class Index(Resource):
    _endpoint = '/'

    @catch
    def get(self):
        return {
            'api_version': 1,
            'info': "Ceph Manager RESTful API server"
        }



class ConfigCluster(Resource):
    _endpoint = '/config/cluster'

    @catch
    def get(self):
        return module.instance.get("config")



class ConfigClusterKey(Resource):
    _endpoint = '/config/cluster/<string:key>'

    @catch
    def get(self, key):
        return module.instance.get("config").get(key, None)



class ConfigOsd(Resource):
    _endpoint = '/config/osd'

    @catch
    def get(self):
        return module.instance.get("osd_map")['flags'].split(',')


    @catch
    def patch(self):
        args = json.loads(request.data)

        commands = []

        valid_flags = set(args.keys()) & set(OSD_FLAGS)
        invalid_flags = list(set(args.keys()) - valid_flags)
        if invalid_flags:
            module.instance.log.warn("%s not valid to set/unset" % invalid_flags)

        for flag in list(valid_flags):
            if args[flag]:
                mode = 'set'
            else:
                mode = 'unset'

            commands.append({
                'prefix': 'osd ' + mode,
                'key': flag,
            })

        return module.instance.submit_request([commands])



class Mon(Resource):
    _endpoint = '/mon'

    @catch
    def get(self):
        return module.instance.get_mons()



class MonName(Resource):
    _endpoint = '/mon/<string:name>'

    @catch
    def get(self, name):
        mon = filter(
            lambda x: x['name'] == name,
            module.instance.get_mons()
        )

        if len(mon) != 1:
                return {'error': 'Failed to identify the monitor node "%s"' % name}

        return mon[0]



class Osd(Resource):
    _endpoint = '/osd'

    @catch
    def get(self):
        # Parse request args
        ids = request.args.getlist('id[]')
        pool_id = request.args.get('pool', None)

        return module.instance.get_osds(ids, pool_id)



class OsdId(Resource):
    _endpoint = '/osd/<int:osd_id>'

    @catch
    def get(self, osd_id):
        osd = module.instance.get_osds([str(osd_id)])
        if len(osd) != 1:
            return {'error': 'Failed to identify the OSD id "%d"' % osd_id}

        return osd[0]


    @catch
    def patch(self, osd_id):
        args = json.loads(request.data)

        commands = []

        osd_map = module.instance.get('osd_map')

        if 'in' in args:
            if args['in']:
                commands.append({
                    'prefix': 'osd in',
                    'ids': [str(osd_id)]
                })
            else:
                commands.append({
                    'prefix': 'osd out',
                    'ids': [str(osd_id)]
                })

        if 'up' in args:
            if args['up']:
                return {'error': "It is not valid to set a down OSD to be up"}
            else:
                commands.append({
                    'prefix': 'osd down',
                    'ids': [str(osd_id)]
                })

        if 'reweight' in args:
            commands.append({
                'prefix': 'osd reweight',
                'id': osd_id,
                'weight': args['reweight']
            })

        return module.instance.submit_request([commands])



class OsdIdCommand(Resource):
    _endpoint = '/osd/<int:osd_id>/command'

    @catch
    def get(self, osd_id):
        osd = module.instance.get_osd_by_id(osd_id)

        if not osd:
            return {'error': 'Failed to identify the OSD id "%d"' % osd_id}

        if osd['up']:
            return OSD_IMPLEMENTED_COMMANDS
        else:
            return []



class OsdIdCommandId(Resource):
    _endpoint = '/osd/<int:osd_id>/command/<string:command>'

    @catch
    def post(self, osd_id, command):
        osd = module.instance.get_osd_by_id(osd_id)

        if not osd:
            return {'error': 'Failed to identify the OSD id "%d"' % osd_id}

        if not osd['up'] or command not in OSD_IMPLEMENTED_COMMANDS:
            return {'error': 'Command "%s" not available' % command}

        return module.instance.submit_request([[{
            'prefix': 'osd ' + command,
            'who': str(osd_id)
        }]])



class Pool(Resource):
    _endpoint = '/pool'

    @catch
    def get(self):
        return module.instance.get('osd_map')['pools']


    @catch
    def post(self):
        args = json.loads(request.data)

        # Check for the required arguments
        pool_name = args.pop('name', None)
        if pool_name == None:
            return {'error': 'You need to specify the pool "name" argument'}

        pg_num = args.pop('pg_num', None)
        if pg_num == None:
            return {'error': 'You need to specify the "pg_num" argument'}

        # Run the pool create command first
        create_command = {
            'prefix': 'osd pool create',
            'pool': pool_name,
            'pg_num': pg_num
        }

        # Check for invalid pool args
        invalid = INVALID_POOL_ARGS(args)
        if invalid:
            return {'error': 'Invalid arguments found: "%s"' % str(invalid)}

        # Schedule the creation and update requests
        return module.instance.submit_request(
            [[create_command]] + \
            POOL_UPDATE_COMMANDS(pool_name, args)
        )



class PoolId(Resource):
    _endpoint = '/pool/<int:pool_id>'

    @catch
    def get(self, pool_id):
        pool = module.instance.get_pool_by_id(pool_id)

        if not pool:
            return {'error': 'Failed to identify the pool id "%d"' % pool_id}

        return pool


    @catch
    def patch(self, pool_id):
        args = json.loads(request.data)

        # Get the pool info for its name
        pool = module.instance.get_pool_by_id(pool_id)
        if not pool:
            return {'error': 'Failed to identify the pool id "%d"' % pool_id}

        # Check for invalid pool args
        invalid = INVALID_POOL_ARGS(args)
        if invalid:
            return {'error': 'Invalid arguments found: "%s"' % str(invalid)}

        # Schedule the update request
        return module.instance.submit_request(POOL_UPDATE_COMMANDS(pool['pool_name'], args))


    @catch
    def delete(self, pool_id):
        pool = module.instance.get_pool_by_id(pool_id)

        if not pool:
            return {'error': 'Failed to identify the pool id "%d"' % pool_id}

        pool_name = pool['pool_name']

        return module.instance.submit_request([[{
            'prefix': 'osd pool delete',
            'pool': pool['pool_name'],
            'pool2': pool['pool_name'],
            'sure': '--yes-i-really-really-mean-it'
        }]])



class Request(Resource):
    _endpoint = '/request'

    @catch
    def get(self):
        states = {}
        for request in module.instance.requests:
            states[request.uuid] = request.get_state()

        return states


    @catch
    @lock
    def delete(self):
        num_requests = len(module.instance.requests)

        module.instance.requests = filter(
            lambda x: not x.is_finished(),
            module.instance.requests
        )

        # Return the number of jobs cleaned
        return num_requests - len(module.instance.requests)



class RequestUuid(Resource):
    _endpoint = '/request/<string:uuid>'

    @catch
    def get(self, uuid):
        request = filter(
            lambda x: x.uuid == uuid,
            module.instance.requests
        )

        if len(request) != 1:
            return {'error': 'Unknown request UUID "%s"' % str(uuid)}

        request = request[0]
        return {
            'uuid': request.uuid,
            'running': map(
                lambda x: (x.command, x.outs, x.outb),
                request.running
            ),
            'finished': map(
                lambda x: (x.command, x.outs, x.outb),
                request.finished
            ),
            'waiting': map(
                lambda x: (x.command, x.outs, x.outb),
                request.waiting
            ),
            'failed': map(
                lambda x: (x.command, x.outs, x.outb),
                request.failed
            ),
            'is_waiting': request.is_waiting(),
            'is_finished': request.is_finished(),
            'has_failed': request.has_failed(),
        }


    @catch
    @lock
    def delete(self, uuid):
        for index in range(len(module.instance.requests)):
            if module.instance.requests[index].uuid == uuid:
                module.instance.requests.pop(index)
                return True

        # Failed to find the job to cancel
        return False



class Server(Resource):
    _endpoint = '/server'

    @catch
    def get(self):
        return module.instance.list_servers()



class ServerFqdn(Resource):
    _endpoint = '/server/<string:fqdn>'

    @catch
    def get(self, fqdn):
        return module.instance.get_server(fqdn)
