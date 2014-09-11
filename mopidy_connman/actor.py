from __future__ import unicode_literals

import logging
import pykka
import pyconnman
import dbus, gobject

from mopidy import service
from mopidy.utils.jsonrpc import private_method

logger = logging.getLogger(__name__)

CONNMAN_SERVICE_NAME = 'connman'

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
gobject.threads_init()


def api_protect(f):
    """
    This decorator protects API calls by ensuring a valid
    pyconnman manager instance is running beforehand.  It
    will raise an exception if pyconnman manager is not
    ready. 
    """
    def wrapper(*args, **kwargs):
        if (args[0].manager is not None):
            return f(*args, **kwargs)
        else:
            raise Exception('Service not ready')
    return wrapper


def make_string(str):
    return dbus.String(str, variant_level=1)


def convert_dbus(obj):
    if (type(obj) is dbus.Byte):
        return int(obj)
    return obj


class ConnectionManager(pykka.ThreadingActor, service.Service):
    """
    ConnectionManager is a network connection manager service.

    The main use-case of this service is to allow the network settings
    to be configured through mopidy thus allowing new/existing WiFi
    networks to be joined or switch over to a LAN connection.
    """
    name = CONNMAN_SERVICE_NAME
    public = True
    agent_path = '/mopidy/wifi_agent'

    # Refer to https://pythonhosted.org/pyconnman for a description of
    # the configuration properties
    readonly_properties = ['State', 'Error', 'Name', 'Type', 'Security',
                           'Strength', 'Nameservers', 'Timeservers',
                           'Domains', 'IPv4', 'IPv6', 'Ethernet']
    readwrite_properties = ['Autoconnect', 'Nameservers.Configuration',
                            'Timeservers.Configuration', 'Domains.Configuration',
                            'IPv4.Configuration', 'IPv6.Configuration']

    def __init__(self, config, core):
        super(ConnectionManager, self).__init__()
        self.config = dict(config['connman'])
        self.manager = None
        self.agent = None

    def _services_changed_handler(self, signal, user_arg, changed, removed):
        """
        Helper to notify when the available connman connections
        has changed
        """
        if (changed):
            for i in changed:
                (_, props) = i
                if 'Name' in props:
                    ret_props = {}
                    for i in props.keys():
                        if (i in self.readonly_properties + self.readwrite_properties):
                            ret_props[i] = convert_dbus(props[i])
                    service.ServiceListener.send('connman_connection_changed', service=self.name,
                                                 connection=props.get('Name'), properties=ret_props)

    def _property_changed_handler(self, signal, user_arg, prop_name, prop_value):
        """
        Helper to notify when a connman property has changed
        """
        props = { prop_name: prop_value } 
        service.ServiceListener.send('connman_property_changed', service=self.name,
                                     properties=props)

    def _get_service_by_name(self, name):
        """
        Helper to find a service (aka connection) by its name
        and return its ConnService object
        """
        for (path, params) in self.manager.get_services():
            if (params.get('Name') == name):
                return pyconnman.ConnService(path)

    def _unregister_wifi_agent(self):
        """
        Helper to unregister a wifi agent if once is registered
        """
        try:
            if (self.agent):
                self.agent.remove_from_connection()
                self.manager.unregister_agent(self.agent_path)
                self.agent = None
        except:
            pass

    @private_method
    def on_start(self):
        """
        Activate the service
        """
        if (self.manager):
            return

        # Create connman manager
        manager = pyconnman.ConnManager()
        manager.add_signal_receiver(self._services_changed_handler,
                                    pyconnman.ConnManager.SIGNAL_SERVICES_CHANGED,
                                    None)
        manager.add_signal_receiver(self._property_changed_handler,
                                    pyconnman.ConnManager.SIGNAL_PROPERTY_CHANGED,
                                    None)
        self.manager = manager

        # Create agent for authenticating WiFi connections
        self._unregister_wifi_agent()
        self.agent = pyconnman.SimpleWifiAgent(self.agent_path)
        self.manager.register_agent(self.agent_path)

        # Enable the services listed in default configuration -
        # anything listed is powered on.  Otherwise it is
        # powered off.
        for (path,_) in self.manager.get_technologies():
            tech = pyconnman.ConnTechnology(path)
            if (tech.Type in self.config['powered'] and not tech.Powered):
                tech.Powered = True

        # Try APIPA if it is enable and the connection is idle
        if (self.get_connection_state() == 'idle' and self.config['apipa_enabled']):
            config = {'Method': make_string('manual'),
                      'Address': make_string(self.config['apipa_ipaddr']),
                      'Netmask': make_string(self.config['apipa_netmask'])}
            s = self._get_service_by_name(self.config['apipa_interface'])
            if (s is not None):
                s.set_property('IPv4.Configuration', config)
                s.connect()

        # Notify listeners
        self.state = service.ServiceState.SERVICE_STATE_STARTED
        service.ServiceListener.send('service_started', service=self.name)
        logger.info('ConnectionManager started')

    @private_method
    def on_stop(self):
        """
        Deactivate the service
        """
        if (self.manager is None):
            return

        # Remove previously installed wifi agent and signal handlers
        self._unregister_wifi_agent()
        self.manager.remove_signal_receiver(pyconnman.ConnManager.SIGNAL_SERVICES_CHANGED)
        self.manager.remove_signal_receiver(pyconnman.ConnManager.SIGNAL_PROPERTY_CHANGED)
        self.manager = None

        # Notify listeners
        self.state = service.ServiceState.SERVICE_STATE_STOPPED
        service.ServiceListener.send('service_stopped', service=self.name)
        logger.info('ConnectionManager stopped')

    @private_method
    def on_failure(self, *args):
        pass

    @private_method
    def stop(self, *args, **kwargs):
        return pykka.ThreadingActor.stop(self, *args, **kwargs)

    @api_protect
    def get_connections(self):
        """
        Obtain a list of existing network connections

        :return: list of network connections
        :rtype: list of 'Name' strings of each connection
        """
        return [params.get('Name') for (_, params) in self.manager.get_services()]

    @api_protect
    def scan(self):
        """
        Scan and refresh the list of available network connections
        (all compatible technologies are scanned).
        This will result in the SIGNAL_SERVICES_CHANGED signal
        being posted for each different technology scanned
        """
        for (path,_) in self.manager.get_technologies():
            tech = pyconnman.ConnTechnology(path)
            if tech.Type in self.config['scannable']:
                tech.scan()

    @api_protect
    def get_connection_state(self):
        """
        Get the global connection state of a system.
        :return: Possible values are "offline", "idle", "ready" and "online".
        :rtype: string
        """
        return self.manager.State

    @api_protect
    def connect(self, conn):
        """
        Connect an available connection

        :param conn: Connection name as returned by :class:`get_connections`
        """
        s = self._get_service_by_name(conn)
        if (s is not None):
            s.connect()

    @api_protect
    def disconnect(self, conn):
        """
        Disconnect an available connection

        :param conn: Connection name as returned by :class:`get_connections`
        """
        s = self._get_service_by_name(conn)
        if (s is not None):
            s.disconnect()

    @api_protect
    def get_connection_properties(self, conn):
        """
        Get available connection properties

        :param conn: Connection name as returned by :class:`get_connections`
        :return: dictionary of properties
        """
        s = self._get_service_by_name(conn)
        if (s is not None):
            ret_props = {}
            props = s.get_property()
            for i in props.keys():
                if (i in self.readonly_properties + self.readwrite_properties):
                    ret_props[i] = convert_dbus(props[i])
            return ret_props

    @api_protect
    def set_connection_properties(self, conn, set_props):
        """
        Set connection properties

        :param conn: Connection name as returned by :class:`get_connections`
        :param set_props: dictionary of readwrite properties
        """
        s = self._get_service_by_name(conn)
        if (s is not None):
            props = s.get_property()
            for i in props.keys():
                if (i in self.readwrite_properties):
                    s.set_property(i, set_props[i])

    @api_protect
    def set_wifi_config(self, conn, config):
        """
        Set WiFi configuration properties dictionary:
        * name: AP name (string)
        * ssid: SSID (string)
        * passphrase: WPS/WEP passphrase (string)
        * wpspin: None or PIN (string)

        Note that 'wpspin' and 'passphrase' are mutually exclusive, i.e.,
        if you are using WPS then you don't need a passphrase.

        For hidden WiFi connections then either a name or SSID
        must be supplied.  If the SSID is not hidden then this may
        be omitted.

        :param conn: Connection name as returned by :class:`get_connections`
            or '*' to denote a wild card connection.
        :param config: configuration properties dictionary
        """
        allowed_config = ['name', 'ssid', 'passphrase', 'wpspin']
        set_config = {}
        for i in config.keys():
            if i in allowed_config:
                set_config[i] = config[i]
        if (conn is not None):
            s = self._get_service_by_name(conn)
            if (s is not None):
                path = s._object.__dbus_object_path__
            else:
                path = None
        else:
            path = '*'
        if (path):
            self.agent.set_service_params(path, **set_config)

    def set_property(self, name, value):
        """
        Set a config property of the plugin/service
        """
        if (name in self.config):
            self.config[name] = value
            service.ServiceListener.send('service_property_changed',
                                         service=self.name,
                                         props={ name: value })
            self.enable()
            self.disable()

    def get_property(self, name):
        """
        Get a config property of the plugin/service
        """
        if (name is None):
            return self.config
        else:
            try:
                value = self.config[name]
                return { name: value }
            except:
                return None

    def enable(self):
        """
        Enable the service
        """
        self.on_start()

    def disable(self):
        """
        Disable the service
        """
        self.on_stop()
