from __future__ import unicode_literals

import os

from mopidy import config, ext, exceptions

__version__ = '0.1.0'


class Extension(ext.Extension):

    dist_name = 'Mopidy-ConnMan'
    ext_name = 'connman'
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        schema['powered'] = config.List()
        schema['scannable'] = config.List()
        schema['apipa_enabled'] = config.Boolean()
        schema['apipa_ipaddr'] = config.String()
        schema['apipa_netmask'] = config.String()
        schema['apipa_interface'] = config.String()
        return schema

    def validate_environment(self):
        try:
            import pyconnman            # noqa
        except ImportError as e:
            raise exceptions.ExtensionError('Unable to find pyconnman module', e)

    def setup(self, registry):
        from .actor import ConnectionManager
        registry.add('frontend', ConnectionManager)
