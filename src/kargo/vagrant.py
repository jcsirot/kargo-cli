#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of Kargo.
#
#    Foobar is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Foobar is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Foobar.  If not, see <http://www.gnu.org/licenses/>.

"""
kargo.vagrant
~~~~~~~~~~~~~

Run VirtualBox VM instances with Varant and generate inventory
"""


import sys
import os
import jinja2
import netaddr
from kargo.inventory import CfgInventory
from kargo.common import get_logger, query_yes_no, run_command, which, id_generator, get_cluster_name
from ansible.utils.display import Display
display = Display()
vagrant_exec = which('vagrant')

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

vagrantfile_tmpl = jinja2.Template("""
Vagrant.configure(2) do |config|
  config.vm.box = "{{ box }}"
  config.ssh.insert_key = false
  config.ssh.private_key_path = ["{{ ssh_private_key }}", "~/.vagrant.d/insecure_private_key"]
  config.vm.provision "file", source: "{{ ssh_public_key }}", destination: "~/.ssh/authorized_keys"
  {% for node_ip in nodes_ips %}
  config.vm.define "node{{ loop.index }}" do |node{{ loop.index }}|
    node{{ loop.index }}.vm.network "private_network", ip: "{{ node_ip }}"
  end
  {% endfor %}
end
""")

class Vagrant(object):
    '''
    Run VirtualBox VM instances with Varant and generate inventory
    '''
    def __init__(self, options):
        self.options = options
        self.inventorycfg = options['inventory_path']
        self.cparser = configparser.ConfigParser(allow_no_value=True)
        self.Cfg = CfgInventory(options, 'vagrant')

        self.vfpath = os.path.join(
            options['kargo_path'],
            'vagrant/Vagrantfile'
        )
        self.logger = get_logger(
            options.get('logfile'),
            options.get('loglevel')
        )
        self.logger.debug('''
             The following options were used to generate the inventory: %s
             ''' % self.options)

    def gen_vagrantfile(self):
        data = self.options
        all_ips = netaddr.IPNetwork(data.network)
        data["nodes_ips"] = []
        for index in range(1, data['count'] + 1):
            data["nodes_ips"].append(str(all_ips[index + 1]))
        self.vagrantfile = vagrantfile_tmpl.render(data)
        self.write_vagrantfile()

    def write_vagrantfile(self):
        '''Write the vagrantfile for instances creation'''
        dir = os.path.dirname(self.vfpath)
        if not os.path.exists(dir):
            os.makedirs(dir)
        try:
            with open(self.vfpath, "w") as vf:
                vf.write(self.vagrantfile)
        except IOError as e:
            display.error(
                'Cant write the Vagrantfile %s: %s'
                % (self.vfpath, e)
            )
            sys.exit(1)

    def write_inventory(self):
        '''Generate the inventory according the instances created'''
        instances = []
        for i, ip in enumerate(self.options['nodes_ips']):
            host = {}
            host['name'] = "node%s" % (i + 1)
            host['ip'] = ip
            instances.append(host)
        self.Cfg.write_inventory(instances)

    def create_instances(self):
        '''Run vagrant up for instances creation'''
        os.environ['VAGRANT_VAGRANTFILE'] = self.vfpath
        cmd = [
            vagrant_exec, 'up', '--destroy-on-error', '--parallel'
        ]
        if not self.options['assume_yes']:
            if not query_yes_no('Create %s VirtualBox VM with Vagrant?' % (
                self.options['count']
                )
            ):
                display.display('Aborted', color='red')
                sys.exit(1)
        rcode, emsg = run_command('Create VirtualBox VM', cmd)
        if rcode != 0:
            self.logger.critical('Cannot create instances: %s' % emsg)
            sys.exit(1)
