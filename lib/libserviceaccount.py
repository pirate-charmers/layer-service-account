from charms import layer

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.core.hookenv import (
    status_set,
    log
)
from subprocess import (
    check_call,
    CalledProcessError
)


class ServiceAccountHelper():
    def __init__(self):
        self.charm_config = hookenv.config()
        self.layer_config = layer.options('service-account')
        self.accounts = {}
        self.groups = {}
        self.group_membership = {}
        self.system_passwd = []
        self.system_groups = []
        self.passwd_path = '/etc/passwd'
        self.groups_path = '/etc/group'

    def install_deps(self):
        fetch.apt_install('passwd')

    def parse_passwd(self):
        passwd_file = open(self.passwd_path, 'r')
        users = []
        for entry in passwd_file:
            user = {}
            fields = entry.strip().split(':')
            user['name'] = fields[0]
            user['id'] = fields[2]
            users.append(user)
        self.system_passwd = users

    def parse_groups(self):
        groups_file = open(self.groups_path, 'r')
        groups = []
        for entry in groups_file:
            group = {}
            fields = entry.strip().split(':')
            group['name'] = fields[0]
            group['id'] = fields[2]
            group['members'] = fields[3].split(',')
            groups.append(group)
        self.system_groups = groups

    def check_user_exists(self, user):
        self.parse_passwd()
        for passwd_user in self.system_passwd:
            if passwd_user['name'] == user:
                return True
        return False

    def add_user(self, user, uid=False):
        self.parse_passwd()
        cmd = []
        if self.check_user_exists(user):
            if uid:
                self.set_uid(user, uid)
        else:
            if uid:
                # default to not adding user groups, this can be
                # done using layer or charm config if needed!
                cmd = ['useradd', '-N', '-r', '-u', uid, user]
            else:
                cmd = ['useradd', '-N', '-r', user]
            try:
                check_call(cmd)
            except CalledProcessError as e:
                status_set('maintenance',
                           'Could not create account {}'.format(user))
                log('Could not create account {}: {}'.format(user, e.output), 'ERROR')
                return False
            else:
                log('Created account {}, UID provided: {}'.format(user, uid), 'DEBUG')

    def set_uid(self, user, uid):
        self.parse_passwd()
        try:
            check_call(['usermod', '-u', uid, user])
        except CalledProcessError as e:
            status_set('maintenance',
                       'Invalid or in-use UID {} for user {} provided'.format(
                           uid,
                           user
                       ))
            log('Invalid or in-use UID {} for account {}: {}'.format(
                    uid,
                    user,
                    e.output),
                'ERROR')
            return False
        else:
            log(
                'Set UID {} for account {}'.format(uid, user),
                'DEBUG'
            )

    def check_uid_conflict(self, user, uid):
        self.parse_passwd()
        for user_entry in self.system_passwd:
            if user_entry['id'] == uid:
                if user_entry['name'] == user:
                    return False
                else:
                    return True
        return False

    def check_group_exists(self, group):
        self.parse_groups()
        for group in self.system_groups:
            if group['name'] == group:
                return True
        return False

    def check_gid_conflict(self, group, gid):
        self.parse_groups()
        for group in self.system_groups:
            if group['id'] == gid:
                if group['name'] == group:
                    return False
                else:
                    return True
        return False

    def add_group(self, group, gid=False):
        self.parse_groups()
        cmd = []
        if self.check_group_exists(group):
            if gid:
                self.set_gid(group, gid)
        else:
            if gid:
                # default to not adding user groups, this can be
                # done using layer or charm config if needed!
                cmd = ['groupadd', '-r', '-g', gid, group]
            else:
                cmd = ['groupadd', '-r', group]
            try:
                check_call(cmd)
            except CalledProcessError as e:
                status_set('maintenance',
                           'Could not create group {}'.format(group))
                log('Could not create group {}: {}'.format(group, e.output), 'ERROR')
                return False
            else:
                log('Created group {}, GID provided: {}'.format(group, gid), 'DEBUG')

    def set_gid(self, group, gid):
        self.parse_groups()
        try:
            check_call(['groupmod', '-g', gid, group])
        except CalledProcessError as e:
            status_set('maintenance',
                       'Invalid or in-use GID {} for group {} provided'.format(
                           gid,
                           group
                       ))
            log('Invalid or in-use GID {} for group {}: {}'.format(
                    gid,
                    group,
                    e.output),
                'ERROR')
            return False
        else:
            log(
                'Set GID {} for group {}'.format(gid, group),
                'DEBUG'
            )

    def check_member_of_group(self, user, group):
        self.parse_groups()
        self.parse_passwd()
        for group_entry in self.system_groups:
            if group_entry == group:
                if user in group['members']:
                    return True
        return False

    def add_group_member(self, group, user):
        try:
            check_call(['usermod', '-a', '-G', group, user])
        except CalledProcessError as e:
            status_set('maintenance',
                       'Invalid group {} being added for user {}'.format(
                           group,
                           user
                       ))
            log('Invalid group {} being added for user {}: {}'.format(
                    group,
                    user,
                    e.output),
                'ERROR')
            return False
        else:
            log(
                'Added group {} for user {}'.format(group, user),
                'DEBUG'
            )

    def build_config(self):
        # read account list
        # this is comma separated
        config_users = self.charm_config['system-additional-users']
        layer_users = self.layer_config['users']
        users = []
        if config_users:
            users.extend(config_users.split(','))
        if layer_users:
            users.extend(layer_users)

        # read UID mapping
        # this is comma separated, user=uid format
        user_mapping = dict()
        config_uidmap = self.charm_config['system-uidmap']
        layer_uidmap = self.layer_config['uidmap']
        if config_uidmap:
            uidmappings = config_uidmap.split(',')
            for uidmapping in uidmappings:
                if '=' in uidmapping:
                    user, uid = uidmapping.split('=')
                    user_mapping[user] = uid
        if layer_uidmap:
            for uid_slice in layer_uidmap:
                for user in uid_slice.keys():
                    user_mapping[user] = uid_slice[user]

        # add user mapping to self.accounts
        for user in users:
            if user in user_mapping.keys():
                self.accounts[user] = user_mapping[user]
            else:
                self.accounts[user] = None

        # read group list
        # this is comma separated
        config_groups = self.charm_config['system-additional-groups']
        layer_groups = self.layer_config['groups']
        groups = []
        if config_groups:
            groups.extend(config_groups.split(','))
        if layer_groups:
            groups.extend(layer_groups)

        # read GID mapping
        # this is comma separated, group=gid format
        group_mapping = {}
        config_gidmap = self.charm_config['system-gidmap']
        layer_gidmap = self.layer_config['gidmap']
        if config_gidmap:
            gidmappings = config_gidmap.split(',')
            for gidmapping in gidmappings:
                if '=' in gidmapping:
                    group, gid = gidmapping.split('=')
                    group_mapping[group] = gid
        if layer_gidmap:
            for gid_slice in layer_gidmap:
                for group in gid_slice.keys():
                    group_mapping[group] = gid_slice[group]

        # add group mapping to self.groups
        for group in groups:
            if group in group_mapping.keys():
                self.groups[group] = group_mapping[group]
            else:
                self.groups[group] = None

        # add memberships to groups
        # this is comma separated, with mapping between group and a list of users
        # the group and list are separated by '='
        # the list of users to ensure are in the group are separated by ':'
        config_membership = self.charm_config['system-group-membership']
        layer_membership = self.layer_config['membership']
        if config_membership:
            membermappings = config_membership.split(',')
            for membermapping in membermappings:
                if '=' in membermapping:
                    group, memberlist = membermapping.split('=')
                    members = []
                    if ':' in memberlist:
                        members = memberlist.split(':')
                    self.group_membership[group] = members
        if layer_membership:
            for group_slice in layer_membership:
                for group in group_slice.keys():
                    self.group_membership[group] = group_slice[group]
        return True

    def process_user_accounts(self):
        # work through user listing, add users if missing
        for user in self.accounts:
            uid = self.accounts[user]
            if self.check_user_exists(user):
                # check for UID mapping, will return None if no mapping
                if uid:
                    # check for UID conflict
                    if self.check_uid_conflict(user, uid):
                        # another user has this UID, error
                        hookenv.status_set('maintenance',
                                           'User {} mapped to UID {}, which already exists'.format(
                                               user, uid))
                        return False
                    else:
                        # update account UID
                        hookenv.status_set('maintenance', 'Updating UID for account {} to {}'.format(
                            user, uid))
                        log('Updated UID for user account {} to {}'.format(user, uid), 'DEBUG')
                        self.set_uid(user, uid)
            else:
                # add user
                self.add_user(user, uid)
                hookenv.status_set('maintenance', 'Adding account {}'.format(user))
                log('Added user account {}'.format(user), 'DEBUG')
        return True

    def process_group_membership(self):
        # work through group listing, add groups if missing
        hookenv.status_set('maintenance', 'Processing group memberships')
        log('Processing group memberships', 'DEBUG')
        for group in self.group_membership.keys():
            for user in self.group_membership[group]:
                if self.check_member_of_group(user, group):
                    # user is already in group
                    log('User {} already in group {}'.format(user, group), 'DEBUG')
                else:
                    # user is not in group, add
                    self.add_group_member(group, user)
                    hookenv.status_set('maintenance', 'Adding group member {} to {}'.format(user, group))
                    log('Added group member {} to {}'.format(user, group), 'DEBUG')
        return True

    def process_groups(self):
        # work through groups, updating groups as needed
        for group in self.groups.keys():
            gid = self.groups[group]
            if self.check_group_exists(group):
                # check for gid mapping, will return None if no mapping
                if gid:
                    # check for gid conflict
                    if self.check_gid_conflict(group, gid):
                        # another group has this gid, error
                        hookenv.status_set('maintenance',
                                           'group {} mapped to gid {}, which already exists'.format(
                                               group, gid))
                        hookenv.log('Group {} mapped to gid {}, which already exists'.format(
                                               group, gid), 'ERROR')
                        return False
                    else:
                        # update account gid
                        hookenv.status_set('maintenance', 'Updating gid for group {} to {}'.format(
                            group, gid))
                        log('Updated gid for group {} to {}'.format(group, gid), 'DEBUG')
                        self.set_gid(group, gid)
            else:
                # add group
                self.add_group(group, gid)
                hookenv.status_set('maintenance', 'Adding group {}'.format(group))
                log('Added group account {}'.format(group), 'DEBUG')
        return True

    def apply_config(self):
        # loop over account and ensure they exist with correct UIDs
        self.process_user_accounts()
        # loop over groups and ensure they exist with correct GIDs
        self.process_groups()
        # loop over memberships, and add users to groups if missing
        self.process_group_membership()

    def update_accounts(self):
        ''' Idempotently configure service accounts and groups '''
        hookenv.status_set('maintenance', 'Updating accounts and groups for service')
        # build current state dictionaries
        self.parse_groups()
        self.parse_passwd()
        # build dictionary of desired state
        self.build_config()
        # apply configuration
        self.apply_config()
        hookenv.status_set('active', 'Processed accounts and groups')
        return True
