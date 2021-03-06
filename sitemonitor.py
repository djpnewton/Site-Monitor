#!/usr/bin/env python

# sample usage: checksites.py eriwen.com nixtutor.com yoursite.org

import pickle
import os
import logging
import time
import re
from optparse import OptionParser, OptionValueError
from smtplib import SMTP
from getpass import getuser
from socket import gethostname, setdefaulttimeout

try:
    from urllib2 import urlopen
    from urllib2 import HTTPError
except ImportError:
    from urllib.request import urlopen
    from urllib.error import HTTPError


def generate_email_alerter(to_addrs, from_addr=None, use_gmail=False,
        username=None, password=None, hostname=None, port=25):

    if not from_addr:
        from_addr = getuser() + "@" + gethostname()

    if use_gmail:
        if username and password:
            server = SMTP('smtp.gmail.com', 587)
            server.starttls()
        else:
            raise OptionValueError('You must provide a username and password to use GMail')
    else:
        if hostname:
            server = SMTP(hostname, port)
        else:
            server = SMTP()
        # server.connect()
        server.starttls()

    if username and password:
        server.login(username, password)

    def email_alerter(message, subject='You have an alert'):
        server.sendmail(from_addr, to_addrs, 'To: %s\r\nFrom: %s\r\nSubject: %s\r\n\r\n%s' % (", ".join(to_addrs), from_addr, subject, message))

    return email_alerter, server.quit


def url_to_host(url):
    return url.split("//")[-1].split(":")[0].split("/")[0]


def get_host_status(url):
    hostname = url_to_host(url)
    response = os.system("ping -c 1 -w2 " + hostname + " > /dev/null 2>&1")
    if response == 0:
        return 'up'
    elif response == 1:
        return 'down (no response from host)'
    elif response == 2:
        return 'down (unknown host)'
    else:
        return 'down (unknown error)'


def get_site_status(url):
    valid_codes = (200, 302, 403)
    try:
        urlfile = urlopen(url)
        status_code = urlfile.code
        if status_code in valid_codes:
            return 'up', urlfile
    except HTTPError, e:
        if e.code in valid_codes:
            return 'up', None
    except:
        pass
    return 'down', None


def compare_site_status(prev_results, alerter):
    '''Report changed status based on previous results'''

    def is_status_changed_type(url, type_, prev_results):
        startTime = time.time()
        urlfile = None
        if type_ == 'web':
            status, urlfile = get_site_status(url)
        elif type_ == 'host':
            status = get_host_status(url)
        endTime = time.time()
        elapsedTime = endTime - startTime
        msg = "%s took %s" % (url, elapsedTime)
        logging.info(msg)

        if status != "up":
            elapsedTime = -1

        friendly_status = '%s: %s is %s. Response time: %s' % (
            type_, url, status, elapsedTime)
        if type_ == 'host':
            friendly_status = '%s: %s is %s. Response time: %s' % (
                type_, url_to_host(url), status, elapsedTime)

        print(friendly_status)
        if 'status' in prev_results and prev_results['status'] != status:
            logging.warning(status)
            # Email status messages
            msg = ''
            if type_ == 'web':
                msg = None if urlfile is None else str(urlfile.info())
            alerter(msg, friendly_status)

        # Save results for later pickling and utility use
        prev_results['status'] = status
        if type_ == 'web':
            prev_results['headers'] = None if urlfile is None else urlfile.info().headers
        prev_results['rtime'] = elapsedTime


    def is_status_changed(url):
        # Create dictionary for url if one doesn't exist (first time url was
        # checked)
        if url not in prev_results:
            prev_results[url] = {}
        for type_ in ('host', 'web'):
            if type_ not in prev_results[url]:
                prev_results[url][type_] = {}
            is_status_changed_type(url, type_, prev_results[url][type_])


    return is_status_changed


def is_internet_reachable():
    '''Checks Google then Yahoo just in case one is down'''
    statusGoogle, urlfileGoogle = get_site_status('http://www.google.com')
    statusYahoo, urlfileYahoo = get_site_status('http://www.yahoo.com')
    if statusGoogle == 'down' and statusYahoo == 'down':
        return False
    return True


def load_old_results(file_path):
    '''Attempts to load most recent results'''
    pickledata = {}
    if os.path.isfile(file_path):
        picklefile = open(file_path, 'rb')
        pickledata = pickle.load(picklefile)
        picklefile.close()
    return pickledata


def store_results(file_path, data):
    '''Pickles results to compare on next run'''
    output = open(file_path, 'wb')
    pickle.dump(data, output)
    output.close()


def normalize_url(url):
    '''If a url doesn't have a http/https prefix, add http://'''
    if not re.match('^http[s]?://', url):
        url = 'http://' + url
    return url


def get_urls_from_file(filename):
    try:
        f = open(filename, 'r')
        filecontents = f.readlines()
        results = []
        for line in filecontents:
            foo = line.strip('\n')
            results.append(foo)
        return results
    except:
        logging.error('Unable to read %s' % filename)
        return []


def get_command_line_options():
    '''Sets up optparse and command line options'''
    usage = "Usage: %prog [options] url"
    parser = OptionParser(usage=usage)
    parser.add_option("-t", "--log-response-time", action="store_true",
            dest="log_response_time",
            help="Turn on logging for response times")

    parser.add_option("-r", "--alert-on-slow-response", action="store_true",
            help="Turn on alerts for response times")

    parser.add_option("--timeout", dest="timeout", type="float",
            help="Set the timeout amount (in seconds).")

    parser.add_option("-g", "--use-gmail", action="store_true", dest="use_gmail",
            help="Send email with Gmail.  Must also specify username and password")

    parser.add_option("--smtp-hostname", dest="smtp_hostname",
            help="Set the stmp server host.")

    parser.add_option("--smtp-port", dest="smtp_port", type="int",
            help="Set the smtp server port.")

    parser.add_option("-u", "--smtp-username", dest="smtp_username",
            help="Set the smtp username.")

    parser.add_option("-p", "--smtp-password", dest="smtp_password",
            help="Set the smtp password.")

    parser.add_option("-s", "--from-addr", dest="from_addr",
            help="Set the from email.")

    parser.add_option("-d", "--to-addrs", dest="to_addrs", action="append",
            help="List of email addresses to send alerts to.")

    parser.add_option("-f", "--from-file", dest="from_file",
            help="Import urls from a text file. Separated by newline.")

    return parser.parse_args()


def main():

    # Get argument flags and command options
    (options, args) = get_command_line_options()

    # Print out usage if no arguments are present
    if len(args) == 0 and options.from_file is None:
        print('Usage:')
        print("\tPlease specify a url like: www.google.com")
        print("\tNote: The http:// is not necessary")
        print('More Help:')
        print("\tFor more help use the --help flag")

    # If the -f flag is set we get urls from a file, otherwise we get them from the command line.
    if options.from_file:
        urls = get_urls_from_file(options.from_file)
    else:
        urls = args

    urls = map(normalize_url, urls)

    # Change logging from WARNING to INFO when logResponseTime option is set
    # so we can log response times as well as status changes.
    if options.log_response_time:
        logging.basicConfig(level=logging.INFO, filename='checksites.log',
                format='%(asctime)s %(levelname)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S')
    else:
        logging.basicConfig(level=logging.WARNING, filename='checksites.log',
                format='%(asctime)s %(levelname)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S')

    # Load previous data
    pickle_file = 'data.pkl'
    pickledata = load_old_results(pickle_file)

    # Add some metadata to pickle
    pickledata['meta'] = {}    # Intentionally overwrite past metadata
    pickledata['meta']['lastcheck'] = time.strftime('%Y-%m-%d %H:%M:%S')

    # create an alerter
    alerter, quiter = generate_email_alerter(options.to_addrs, from_addr=options.from_addr,
                          use_gmail=options.use_gmail,
                          username=options.smtp_username, password=options.smtp_password,
                          hostname=options.smtp_hostname, port=options.smtp_port)

    # Set timeout
    setdefaulttimeout(options.timeout)

    # Check sites only if Internet is_available
    if is_internet_reachable():
        status_checker = compare_site_status(pickledata, alerter)
        list(map(status_checker, urls))
    else:
        logging.error('Either the world ended or we are not connected to the net.')

    # Store results in pickle file
    store_results(pickle_file, pickledata)

    quiter()

if __name__ == '__main__':
    # First arg is script name, skip it
    main()
