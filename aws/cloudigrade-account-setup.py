"""
Utility script for setting up a new AWS account for developer use.

Intended to be run by someone with admin-level privileges in the account.
"""
import csv
import json
import random
import string

import boto3
import click

PASSWORD_CHARS = string.punctuation + string.hexdigits
for char in ['\\', '/', '\'', '"']:
    PASSWORD_CHARS = PASSWORD_CHARS.replace(char, '')


def set_account_alias(alias, iam_client=None):
    """Attempt to set the desired account alias. Abort if already set."""
    if iam_client is None:
        iam_client = boto3.client('iam')
    aliases = iam_client.list_account_aliases().get('AccountAliases', [])
    if len(aliases):
        print(f'warning: account aliases already set with {aliases}')
    else:
        iam_client.create_account_alias(AccountAlias=alias)
        print(f'account alias set to "{alias}"')


def configure_user_group(groupname, iam_client=None):
    """Ensure the group exists with no policies set."""
    if iam_client is None:
        iam_client = boto3.client('iam')
    groups = iam_client.list_groups().get('Groups', [])
    matches = [group for group in groups if group['GroupName'] == groupname]
    if matches:
        print(f'warning: group "{groupname}" already exists')
    else:
        group = iam_client.create_group(GroupName=groupname)
        print(f'group "{groupname}" created')
    group_policies = iam_client.list_attached_group_policies(GroupName=groupname)
    for policy in group_policies.get('AttachedPolicies', []):
        iam_client.detach_group_policy(GroupName=groupname, PolicyArn=policy['PolicyArn'])
        print(f'warning: detached policy "{policy["PolicyName"]}" from group "{groupname}"')


def create_users(new_usernames, groupname, keys, iam_client=None, iam_resource=None):
    """Create users, assign to the group, and reset their credentials."""
    if iam_client is None:
        iam_client = boto3.client('iam')
    if iam_resource is None:
        iam_resource = boto3.resource('iam')

    secrets = []
    existing_usernames = [user['UserName'] for user in iam_client.list_users().get('Users', [])]

    # create the users
    for username in new_usernames:
        if username in existing_usernames:
            print(f'warning: username "{username}" already exists')
        else:
            user = iam_client.create_user(UserName=username)
            print(f'created user "{username}"')

    # put each user in the group
    for username in new_usernames:
        groups = iam_client.list_groups_for_user(UserName=username).get('Groups', [])
        groupnames = [group['GroupName'] for group in groups]
        if groupname in groupnames:
            print(f'warning: user "{username}" already in group "{groupname}"')
        else:
            iam_client.add_user_to_group(UserName=username, GroupName=groupname)
            print(f'added user "{username}" to group "{groupname}"')

    # reset credentials for each user
    for username in new_usernames:
        new_password = ''.join([random.choice(PASSWORD_CHARS) for _ in range(32)])

        # set an initial password and require it to be reset on first login
        login_profile = iam_resource.LoginProfile(username)
        try:
            login_profile.update(Password=new_password, PasswordResetRequired=True)
        except iam_resource.meta.client.exceptions.NoSuchEntityException:
            login_profile.create(Password=new_password, PasswordResetRequired=True)

        # destroy any existing access keys
        access_keys = iam_client.list_access_keys(UserName=username).get('AccessKeyMetadata', [])
        for old_access_key in access_keys:
            iam_client.delete_access_key(UserName=username, AccessKeyId=old_access_key['AccessKeyId'])
            print(f'warning: deleted old access key for "{username}"')

        # generate a new access key
        if keys:
            access_key = iam_client.create_access_key(UserName=username).get('AccessKey',{})
            secrets.append((username, new_password, access_key['AccessKeyId'], access_key['SecretAccessKey']))
            print(f'new access key generated for "{username}"')
        else:
            secrets.append((username, new_password, None, None))
            print(f'new access key NOT generated for "{username}"')

        print(f'user "{username}" credentials have been reset')

    return secrets


def configure_account_password_policy(iam_resource=None):
    """Assign an appropriate password policy to the account."""
    if iam_resource is None:
        iam_resource = boto3.resource('iam')
    account_password_policy = iam_resource.AccountPasswordPolicy()
    account_password_policy.update(
        MinimumPasswordLength=16,
        RequireSymbols=True,
        RequireNumbers=True,
        RequireUppercaseCharacters=True,
        RequireLowercaseCharacters=True,
        AllowUsersToChangePassword=True,
        # MaxPasswordAge=0,  # https://boto3.readthedocs.io/en/latest/reference/services/iam.html#IAM.AccountPasswordPolicy.update
        PasswordReusePrevention=16,
        HardExpiry=False
    )
    print('account_password_policy updated')
    attrs = [
        'allow_users_to_change_password',
        'expire_passwords',
        'hard_expiry',
        'max_password_age',
        'minimum_password_length',
        'password_reuse_prevention',
        'require_lowercase_characters',
        'require_numbers',
        'require_symbols',
        'require_uppercase_characters',
    ]
    for attr in attrs:
        print(f'account password policy {attr} is {getattr(account_password_policy, attr)}')


def dump_new_logins(alias, secrets, keys):
    """Dump the created users and credentials to CSV files for distribution."""
    login_url = f'https://{alias}.signin.aws.amazon.com/console'
    for username, password, access_key, secret_access_key in secrets:
        filepath = f'{alias}-{username}-credentials.csv'
        data = {
            'Console login link': login_url,
            'User name': username,
            'Password': password,
        }
        if keys:
            data.update({
                'Access key id': access_key,
                'Secret access key': secret_access_key,
            })
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=data.keys(), quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerow(data)
        print(f'wrote login info to "{filepath}"')


def delete_policy_if_exists(policy_name, iam_client=None):
    """Delete the policy if it exists."""
    if iam_client is None:
        iam_client = boto3.client('iam')
    policies = iam_client.list_policies(Scope='Local').get('Policies', [])
    for policy in policies:
        if policy['PolicyName'] == policy_name:
            iam_client.delete_policy(PolicyArn=policy['Arn'])
            print(f'warning: deleted existing policy "{policy_name}"')


def create_policy_for_acting_as_customer(iam_client=None):
    """Create the policy for acting as a customer."""
    if iam_client is None:
        iam_client = boto3.client('iam')
    policy_name = 'cloudigrade-engineer-as-customer'
    delete_policy_if_exists(policy_name, iam_client=iam_client)
    policy = iam_client.create_policy(
        PolicyName=policy_name,
        Description='For cloudigrade engineers to simulate customer activity.',
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "VisualEditor0",
                    "Effect": "Allow",
                    "Action": [
                        "iam:*",
                        "cloudtrail:*",
                        "ec2:*"
                    ],
                    "Resource": "*"
                }
            ]
        })
    )
    print(f'created policy "{policy_name}"')
    return policy


def create_policy_for_running_cluster(iam_client=None):
    """Create the policy for running the houndigrade cluster."""
    if iam_client is None:
        iam_client = boto3.client('iam')
    policy_name = 'cloudigrade-engineer-as-cluster'
    delete_policy_if_exists(policy_name, iam_client=iam_client)
    policy = iam_client.create_policy(
        PolicyName=policy_name,
        Description='For cloudigrade engineers to run the houndigrade cluster.',
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "VisualEditor0",
                    "Effect": "Allow",
                    "Action": [
                        "sns:*",
                        "s3:*",
                        "ec2:*",
                        "sqs:*"
                    ],
                    "Resource": "*"
                }
            ]
        })
    )
    print(f'created policy "{policy_name}"')
    return policy




@click.command()
@click.option('--alias', help='desired account alias')
@click.option('--customer', help='enable policy for acting as a customer', is_flag=True)
@click.option('--cluster', help='enable policy for running the cluster', is_flag=True)
@click.option('--groupname', default='cloudigrade-engineer', help='desired group name')
@click.option('--keys/--no-keys', default=False)
@click.argument('new_usernames', nargs=-1, type=click.UNPROCESSED)
def configure(alias, customer, cluster, groupname, keys, new_usernames):
    new_usernames = set(new_usernames)
    iam_client = boto3.client('iam')
    iam_resource = boto3.resource('iam')
    configure_account_password_policy(iam_resource=iam_resource)
    if alias is not None:
        set_account_alias(alias, iam_client=iam_client)
    if groupname is not None:
        configure_user_group(groupname, iam_client=iam_client)
    policies = []
    if customer:
        policies.append(create_policy_for_acting_as_customer(iam_client=iam_client)['Policy'])
    if cluster:
        policies.append(create_policy_for_running_cluster(iam_client=iam_client)['Policy'])
    if groupname is not None:
        for policy in policies:
            iam_client.attach_group_policy(GroupName=groupname, PolicyArn=policy['Arn'])
            print(f'policy "{policy["PolicyName"]}" attached to group')

    if new_usernames:
        actual_alias = iam_client.list_account_aliases().get('AccountAliases', [])[0]
        secrets = create_users(new_usernames, groupname, keys, iam_client=iam_client, iam_resource=iam_resource)
        dump_new_logins(actual_alias, secrets, keys)


if __name__ == '__main__':
    configure()
