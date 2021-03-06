
# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Rules engine for CloudSQL acls"""
from collections import namedtuple
import itertools
import re

# pylint: disable=line-too-long
from google.cloud.security.common.gcp_type import cloudsql_access_controls as csql_acls
# pylint: enable=line-too-long
from google.cloud.security.common.util import log_util
from google.cloud.security.scanner.audit import base_rules_engine as bre
from google.cloud.security.scanner.audit import errors as audit_errors

LOGGER = log_util.get_logger(__name__)


# TODO: move this to utils since it's used in more that one engine
def escape_and_globify(pattern_string):
    """Given a pattern string with a glob, create actual regex pattern.

    To require > 0 length glob, change the "*" to ".+". This is to handle
    strings like "*@company.com". (THe actual regex would probably be
    ".*@company.com", except that we don't want to match zero-length
    usernames before the "@".)

    Args:
        pattern_string: The pattern string of which to make a regex.

    Returns:
    The pattern string, escaped except for the "*", which is
    transformed into ".+" (match on one or more characters).
    """

    return '^{}$'.format(re.escape(pattern_string).replace('\\*', '.+'))


class CloudSqlRulesEngine(bre.BaseRulesEngine):
    """Rules engine for CloudSQL acls"""

    def __init__(self, rules_file_path):
        """Initialize.

        Args:
            rules_file_path: file location of rules
        """
        super(CloudSqlRulesEngine,
              self).__init__(rules_file_path=rules_file_path)
        self.rule_book = None

    def build_rule_book(self):
        """Build CloudSQLRuleBook from the rules definition file."""
        self.rule_book = CloudSqlRuleBook(self._load_rule_definitions())

    # pylint: disable=arguments-differ
    def find_policy_violations(self, cloudsql_acls,
                               force_rebuild=False):
        """Determine whether CloudSQL acls violates rules."""
        violations = itertools.chain()
        if self.rule_book is None or force_rebuild:
            self.build_rule_book()
        resource_rules = self.rule_book.get_resource_rules()

        for rule in resource_rules:
            violations = itertools.chain(violations,
                                         rule.\
                                         find_policy_violations(cloudsql_acls))
        return violations

    def add_rules(self, rules):
        """Add rules to the rule book."""
        if self.rule_book is not None:
            self.rule_book.add_rules(rules)


class CloudSqlRuleBook(bre.BaseRuleBook):
    """The RuleBook for CloudSQL acls resources."""

    def __init__(self, rule_defs=None):
        """Initialization.

        Args:
            rule_defs: rule definitons
        """
        super(CloudSqlRuleBook, self).__init__()
        self.resource_rules_map = {}
        if not rule_defs:
            self.rule_defs = {}
        else:
            self.rule_defs = rule_defs
            self.add_rules(rule_defs)

    def add_rules(self, rule_defs):
        """Add rules to the rule book"""
        for (i, rule) in enumerate(rule_defs.get('rules', [])):
            self.add_rule(rule, i)

    def add_rule(self, rule_def, rule_index):
        """Add a rule to the rule book.

        Args:
            rule_def: A dictionary containing rule definition properties.
            rule_index: The index of the rule from the rule definitions.
            Assigned automatically when the rule book is built.
        """

        resources = rule_def.get('resource')

        for resource in resources:
            resource_ids = resource.get('resource_ids')

            if not resource_ids or len(resource_ids) < 1:
                raise audit_errors.InvalidRulesSchemaError(
                    'Missing resource ids in rule {}'.format(rule_index))

            instance_name = rule_def.get('instance_name')
            authorized_networks = rule_def.get('authorized_networks')
            ssl_enabled = rule_def.get('ssl_enabled')

            if (instance_name is None) or (authorized_networks is None) or\
             (ssl_enabled is None):
                raise audit_errors.InvalidRulesSchemaError(
                    'Faulty rule {}'.format(rule_def.get('name')))

            rule_def_resource = csql_acls.CloudSqlAccessControl(
                escape_and_globify(instance_name),
                escape_and_globify(authorized_networks),
                ssl_enabled)

            rule = Rule(rule_name=rule_def.get('name'),
                        rule_index=rule_index,
                        rules=rule_def_resource)

            resource_rules = self.resource_rules_map.get(rule_index)

            if not resource_rules:
                self.resource_rules_map[rule_index] = rule

    def get_resource_rules(self):
        """Get all the resource rules for (resource, RuleAppliesTo.*).

        Args:
            resource: The resource to find in the ResourceRules map.

        Returns:
            A list of ResourceRules.
        """
        resource_rules = []

        for resource_rule in self.resource_rules_map:
            resource_rules.append(self.resource_rules_map[resource_rule])

        return resource_rules


class Rule(object):
    """Rule properties from the rule definition file.
    Also finds violations.
    """

    def __init__(self, rule_name, rule_index, rules):
        """Initialize.

        Args:
            rule_name: Name of the loaded rule
            rule_index: The index of the rule from the rule definitions
            rules: The rules from the file
        """
        self.rule_name = rule_name
        self.rule_index = rule_index
        self.rules = rules

    def find_policy_violations(self, cloudsql_acl):
        """Find CloudSQL policy acl violations in the rule book.

        Args:
            cloudsql_acl: CloudSQL ACL resource

        Returns:
            Returns RuleViolation named tuple
        """
        filter_list = []
        if self.rules.instance_name != '^.+$':
            instance_name_bool = re.match(self.rules.instance_name,
                                          cloudsql_acl.instance_name)
        else:
            instance_name_bool = True

        if self.rules.authorized_networks != '^.+$':
            authorized_networks_regex = re.compile(self.rules.\
                                                   authorized_networks)
            filter_list = filter(authorized_networks_regex.match,
                                 cloudsql_acl.authorized_networks)

            authorized_networks_bool = bool(filter_list)
        else:
            authorized_networks_bool = True

        ssl_enabled_bool = (self.rules.ssl_enabled == cloudsql_acl.ssl_enabled)

        should_raise_violation = (
            (instance_name_bool is not None and instance_name_bool) and\
            (authorized_networks_bool is not None and\
             authorized_networks_bool) and
            (ssl_enabled_bool is not None and ssl_enabled_bool))

        if should_raise_violation:
            yield self.RuleViolation(
                resource_type='project',
                resource_id=cloudsql_acl.project_number,
                rule_name=self.rule_name,
                rule_index=self.rule_index,
                violation_type='CLOUD_SQL_VIOLATION',
                instance_name=cloudsql_acl.instance_name,
                authorized_networks=cloudsql_acl.authorized_networks,
                ssl_enabled=cloudsql_acl.ssl_enabled)

    # Rule violation.
    # resource_type: string
    # resource_id: string
    # rule_name: string
    # rule_index: int
    # violation_type: CLOUD_SQL_VIOLATION
    # instance_name: string
    # authorized_networks: string
    # ssl_enabled: string
    RuleViolation = namedtuple('RuleViolation',
                               ['resource_type', 'resource_id', 'rule_name',
                                'rule_index', 'violation_type',
                                'instance_name', 'authorized_networks',
                                'ssl_enabled'])
