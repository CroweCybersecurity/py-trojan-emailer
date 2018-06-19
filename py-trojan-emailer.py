#! python3

import os
import csv
import logging
import smtplib
import argparse
from time import sleep
from email import encoders
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart


def send_email(recipient_email_addresss, cli_arguments, replacement_values=None):
    """Build and send an email"""

    # Create an email and setup headers
    email_message = MIMEMultipart('alternative')
    email_message['Subject'] = cli_arguments.email_subject
    email_message['To'] = recipient_email_addresss
    if cli_arguments.hide_source_email is False:
        email_message['From'] = '"{0}" <{1}>'.format(cli_arguments.sender_display_name, cli_arguments.sender_address)
    else:
        space_hack = (' ' * 200) + '|'
        email_message['From'] = '"{0} {2}" <{1}>'.format(cli_arguments.sender_display_name, cli_arguments.sender_address, space_hack)
    email_message['X-Priority'] = cli_arguments.message_priority

    # Add a spoofed carbon copy if provided
    if cli_arguments.cc_display_name is not None:
        email_message['CC'] = '"{0}" <>'.format(cli_arguments.cc_display_name)

    # Setup the email body
    email_body = cli_arguments.email_body.read()
    # Reset the cursor to the start in order to read the file multiple times
    cli_arguments.email_body.seek(0)

    # Replace placeholder values if substitution data is provided
    if replacement_values is not None:
        for key, value in replacement_values.items():
            replacement_egg = '${0}$'.format(key)
            logging.debug('Replacing [%s] with [%s]', replacement_egg, value)
            email_body = email_body.replace(replacement_egg, value)

    encoded_message = MIMEText(email_body, cli_arguments.message_format)
    email_message.attach(encoded_message)

    # Add an attachment if provided
    if cli_arguments.email_attachment is not None:
        attachment_file_name = os.path.basename(cli_arguments.email_attachment.name)

        email_message_attachment = MIMEBase('application', 'octet-stream')
        email_message_attachment.set_payload(cli_arguments.email_attachment.read())
        # Reset the cursor to the start of the file in case it needs to be sent multiple times
        cli_arguments.email_attachment.seek(0)
        encoders.encode_base64(email_message_attachment)
        email_message_attachment['Content-Disposition'] = 'attachment; filename= {0}'.format(attachment_file_name)

        email_message.attach(email_message_attachment)

    # Create a connection to the SMTP server and deliver the message
    with smtplib.SMTP(cli_arguments.smtp_server, cli_arguments.smtp_port) as smtp_server:

        # Setup a TLS connection and authenticate to the SMTP service
        if cli_arguments.smtp_username is not None:
            logging.info('Logging into %s on port %i using user: %s', cli_arguments.smtp_server,
                         cli_arguments.smtp_port, cli_arguments.smtp_username)
            smtp_server.ehlo()
            smtp_server.starttls()
            smtp_server.ehlo()
            smtp_server.login(cli_arguments.smtp_username, cli_arguments.smtp_password)

        # continue sending email
        logging.info('Sending an email to %s', recipient_email_addresss)

        # perform SPF spoofing by setting the envelope and message headers with different recipients
        if cli_arguments.envelope_sender_address is not None:
            smtp_server.send_message(email_message, from_addr=cli_arguments.envelope_sender_address)
        else:
            smtp_server.send_message(email_message)


def send_multiple_emails(recipient_file, cli_arguments):
    """Process through a CSV containing multiple recipients and optional message substitution data.
       After some basic error validation the user must confirm recipients are appropriate before mass emailing begins."""

    recipient_information = list(csv.DictReader(recipient_file))

    # Confirm at least one recipient is provided
    if len(recipient_information) < 1:
        logging.error('The provided CSV is too short. There should be at least two rows. '
                      'The header row and one row of data.')
        exit()

    # Confirm the required field of EmailAddress is present
    if 'EmailAddress' not in recipient_information[0]:
        logging.error('Looks like the EmailAddress field was not included in the recipient CSV file. '
                      'This is a required item and must be included.')
        exit()

    # Required the user to perform a sanity check before sending multiple emails
    logging.info('The following %i emails are about to be sent:', len(recipient_information))

    for individual_recipient in recipient_information:
        logging.info('--------------------')
        for key, value in individual_recipient.items():
            logging.info('[%s] %s', key, value)

    if confirm_action('Before multiple emails are sent, do these values look correct?', 'y') is False:
        logging.warning('User termination. Improper values detected.')
        exit()

    # Start sending emails to all recipients
    for individual_recipient in recipient_information:
        logging.debug('Processing an email to %s', individual_recipient['EmailAddress'])
        send_email(individual_recipient['EmailAddress'], cli_arguments, individual_recipient)
        sleep(cli_arguments.sending_delay)


def confirm_action(question, default):
    """Ask the user to answer a yes/no questions. The assumption is the default
    response is what is desired. This will return True. The inverse response
    will return False."""

    if default == 'y':
        prompt = ' [Y/n] '
    elif default == 'n':
        prompt = ' [y/N] '

    while True:
        logging.info(question + prompt)
        choice = input('Input -> ').lower()

        if (choice == default) or (choice == ''):
            return True
        elif (choice == 'y' or choice == 'n') and choice != default:
            return False
        else:
            logging.warning('Invalid input supplied')


def main():
    """Build and parse command line arguments, setup logging, and perform general program orchestration."""

    # Command line arguments
    parser = argparse.ArgumentParser(description="A Python wrapper for sending email to SMTP services.",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--debug', dest='logging_level', action='store_const', const=logging.DEBUG,
                        default=logging.INFO, help='enable debug logging')

    sender_group = parser.add_argument_group('sender options', 'options related to who is sending the message')
    sender_group.add_argument('-f', dest='sender_address', required=True, help='the sending email address')
    sender_group.add_argument('--envelope_from', dest='envelope_sender_address',
                              help='set an alternate message envelope sending email address for SPF spoofing [EXPERIMENTAL]')
    sender_group.add_argument('-d', dest='sender_display_name', required=True, help='the sending display name')
    sender_group.add_argument('--hide-email', dest='hide_source_email', action='store_true', default=False, help='hide sender email address from view in target\'s mailbox')
    sender_group.add_argument('--blank-copy', dest='cc_display_name',
                              help='add a carbon copy display name with no email address for CC spoofing')

    recipient_group = parser.add_argument_group('recipient options', 'options related to who is receiving the message')
    mutually_exclusive_recipient_group = recipient_group.add_mutually_exclusive_group(required=True)
    mutually_exclusive_recipient_group.add_argument('-r', dest='recipient', help='the receiving address')
    mutually_exclusive_recipient_group.add_argument('-R', dest='recipient_file', type=argparse.FileType('r'),
                                                    help='a file containing a list of receiving addresses')

    message_group = parser.add_argument_group('message options', 'options related to email message being sent')
    message_group.add_argument('-s', dest='email_subject', required=True, help='the subject of the email')
    message_group.add_argument('-m', dest='email_body', type=argparse.FileType('r'), required=True,
                               help='a file containing the email body')
    message_group.add_argument('-a', dest='email_attachment', type=argparse.FileType('rb'),
                               help='an attachment to include with the email')
    message_group.add_argument('--encoding', dest='message_format', choices=['plain', 'html'], default='html',
                               help='the encoding of the email body')
    message_group.add_argument('--priority', dest='message_priority', choices=['1', '3', '5'], default='3',
                               help='the priority of the email, lower is greater importance')

    server_group = parser.add_argument_group('server options', 'options related to the SMTP server sending the message')
    server_group.add_argument('-i', dest='smtp_server', required=True, help='the IP address or FQDN of the SMTP server')
    server_group.add_argument('--port', dest='smtp_port', type=int, default=25, help='the port of the SMTP server')
    server_group.add_argument('--delay', dest='sending_delay', type=int, default=10,
                              help='the number of seconds to wait between sending each message')
    server_group.add_argument('--username', dest='smtp_username', help='username for SMTP authentication')
    server_group.add_argument('--password', dest='smtp_password', help='password for SMTP authentication')
    cli_args = parser.parse_args()

    # Logging setup
    logging.basicConfig(format='%(levelname)-8s %(message)s', level=cli_args.logging_level)

    # Conditional requirement processing for command line arguments
    if ((cli_args.smtp_username is not None or cli_args.smtp_password is not None) and
       (cli_args.smtp_username is None or cli_args.smtp_password is None)):
       logging.error('Both a username and password is required for SMTP authentication')
       exit()

    # Entry point processing
    if cli_args.recipient is not None:
        logging.info('Processing a single email to %s', cli_args.recipient)
        send_email(cli_args.recipient, cli_args)
    elif cli_args.recipient_file is not None:
        logging.info('Processing multiple emails to individuals in the file at %s', cli_args.recipient_file.name)
        send_multiple_emails(cli_args.recipient_file, cli_args)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.info('Program termination requested by user')
