****************************
Mopidy-ConnMan
****************************

.. image:: https://pypip.in/version/Mopidy-ConnMan/badge.png?latest
    :target: https://pypi.python.org/pypi/Mopidy-ConnMan/
    :alt: Latest PyPI version

.. image:: https://pypip.in/download/Mopidy-ConnMan/badge.png
    :target: https://pypi.python.org/pypi/Mopidy-ConnMan/
    :alt: Number of PyPI downloads

.. image:: https://travis-ci.org/liamw9534/mopidy-connman.png?branch=master
    :target: https://travis-ci.org/liamw9534/mopidy-connman
    :alt: Travis CI build status

.. image:: https://coveralls.io/repos/liamw9534/mopidy-connman/badge.png?branch=master
   :target: https://coveralls.io/r/liamw9534/mopidy-connman?branch=master
   :alt: Test coverage

`Mopidy <http://www.mopidy.com/>`_ extension for network connection management.


Installation
============

Install by running::

    pip install Mopidy-ConnMan

Or, if available, install the Debian/Ubuntu package from `apt.mopidy.com
<http://apt.mopidy.com/>`_.


Configuration
=============

Dbus
----

Before starting Mopidy, you must ensure the 'audio' user group has dbus permissions
for managing network connections.  This can be done by adding the following policy
section into the file ``/etc/dbus-1/system.d/connman.conf``::

    <!-- allow users of audio group to communicate with connmand -->
    <policy group="audio">
        <allow send_destination="net.connman"/>
    </policy>


Note: If you are running as a different group or user then you can substitute the above
policy for your own requirements.


Extension
---------

Add the following section to your Mopidy configuration file following installation::

    [connman]
    enabled = true
    powered = wifi, ethernet
    scannable = wifi

The ``powered`` configuration parameter is a list of technologies that should be powered on at
start-up.  Any technology listed not powered on already will be powered on.  Supported technologies
are 'wifi' and 'ethernet'.

The ``scannable`` configuration parameter defines which technologies to scan in accordance with the
``scan()`` API call.  If this list is empty then no technologies shall be scanned.  Supported
scannable technologies are 'wifi' only.


HTTP API
--------

- To get the overall network connection state, use ``mopidy.connman.getConnectionState()``
- To obtain a list of available connections, use ``mopidy.connman.getConnections()``
- To connect an available connection, use ``mopidy.connman.connect()``
- To disconnect an available connection, use ``mopidy.connman.disconnect()``
- To configure authentication for wifi, use ``mopidy.connman.setWifiConfig()``
- To get or set a connection's properties, use ``mopidy.connman.getConnectionProperties()`` and
``mopidy.connman.setConnectionProperties()`` respectively.
- Extension properties may be get/set dynamically using ``getProperty()`` and ``setProperty()``
respectively.  Setting an extension property will result in the extension being restarted.


Project resources
=================

- `Source code <https://github.com/liamw9534/mopidy-connman>`_
- `Issue tracker <https://github.com/liamw9534/mopidy-connman/issues>`_
- `Download development snapshot <https://github.com/liamw9534/mopidy-connman/archive/master.tar.gz#egg=mopidy-connman-dev>`_


Changelog
=========


v0.1.0 (UNRELEASED)
----------------------------------------

- Initial release.
