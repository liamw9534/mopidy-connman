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
        self = args[0]
        if (self.manager):
            f(*args, **kwargs)
        else:
            raise Exception('Service not ready')
    return wrapper


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

    def _services_changed_handler(self, signal, user_arg, services):
        """
        Helper to notify when the available connman connections
        has changed
        """ 
        service.ServiceListener.send('connman_connections_changed', service=self.name,
                                     connections=[{'Name':s.Name, 'Type':s.Type} for s in services])

    def _property_changed_handler(self, signal, user_arg, prop):
        """
        Helper to notify when a connman property has changed
        """ 
        service.ServiceListener.send('connman_property_changed', service=self.name,
                                     property=prop)

    def _get_service_by_name(self, name):
        """
        Helper to find a service (aka connection) by its name
        and return its ConnService object
        """
        for (path, params) in self.manager.get_services():
            if (params.Name == name):
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
        for t in self.manager.get_technologies():
            tech = pyconnman.ConnTechnology(t)
            if tech.Name in self.config['powered']:
                tech.Powered = True
            else:
                tech.Powered = False

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
        return [params.Name for (_, params) in self.manager.get_services()]

    @api_protect
    def scan(self):
        """
        Scan and refresh the list of available network connections
        (all compatible technologies are scanned).
        This will result in the SIGNAL_SERVICES_CHANGED signal
        being posted for each different technology scanned
        """
        for t in self.manager.get_technologies():
            tech = pyconnman.ConnTechnology(t)
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
        if (s):
            s.connect()

    @api_protect
    def disconnect(self, conn):
        """
        Disconnect an available connection

        :param conn: Connection name as returned by :class:`get_connections`
        """
        s = self._get_service_by_name(conn)
        if (s):
            s.disconnect()

    @api_protect
    def get_connection_properties(self, conn):
        """
        Get available connection properties

        :param conn: Connection name as returned by :class:`get_connections`
        :return: dictionary of properties
        """
        s = self._get_service_by_name(conn)
        if (s):
            ret_props = {}
            props = s.get_property()
            for i in props.keys():
                if (i in self.readonly_properties + self.readwrite_properties):
                    ret_props[i] = props[i]
            return ret_props

    @api_protect
    def set_connection_properties(self, conn, set_props):
        """
        Set connection properties

        :param conn: Connection name as returned by :class:`get_connections`
        :param set_props: dictionary of readwrite properties
        """
        s = self._get_service_by_name(conn)
        if (s):
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
            if (s):
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
