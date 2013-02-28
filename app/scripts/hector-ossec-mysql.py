#!/usr/bin/python
"""
This script is part of HECTOR.
by Justin C. Klein Keane <jukeane@sas.upenn.edu>
Last modified: 27 February, 2013

This script is a daemonized log observer that parses OSSEC logs and then
imports them into the HECTOR database.  It is intended to be run from the
/etc/init.d/hector-ossec-mysql script included with HECTOR
"""
import MySQLdb
import time
import re
import sys
import syslog

# Credentials used for the database connection
HOST = 'localhost'
USERNAME = 'root'
PASSWORD = ''
DB = 'hector'
PORT = 3306

class LogEntry: 
  """ This is just the object that we craft to 
  hold the OSSEC log file entry (since it is 
  a multi-line log)
  """
  # This is the OSSEC alert id (ex: 1297702559.16083181)
  ossec_alert_id = None
  # The date the alert was generated (ex: 2011 Feb 14 11:55:59)
  date = None
  # The host_id from the hector.host table
  host_id = None
  # The log the alert came from (ex: (www.sas.upenn.edu) 128.91.55.19->/var/log/httpd/error_log)
  alert_log = None
  # The rule id from the hector.ossec_rules table
  rule_id = None
  # The actual body of the log entry that caused the alert, into ossec_alerts.rule_log
  message = None
  
  # Other self explanatory messages
  src_ip = user = conn = None
  
  def __init__(self, conn):
    """ Accepts the database connection so it can be reused. """
    self.conn = conn
    
  def clear(self):
    """ Delete all data so the object can be re-used."""
    self.ossec_alert_id = None
    self.date = None
    self.host_id = None
    self.alert_log = None
    self.rule_id = None
    self.src_ip = None
    self.user = None
    self.message = None
  
  def get_ossec_alert_id(self):
    """ Return the OSSEC alert id (ex: 1297702559.16083181) or a blank."""
    if self.ossec_alert_id is None:
      return ""
    else:
      return self.ossec_alert_id
    
  def get_date(self):
    """ Return the date or a blank date ('0000-00-00 00:00:00')"""
    if self.date is None:
      return "0000-00-00 00:00:00"
    else:
      return self.date
    
  def get_host_id(self):
    """Return the host id from the database, or zero."""
    if self.host_id is None:
      return 0
    else:
      return self.host_id
    
  def get_alert_log(self):
    """Return the log this alert was generated from, or blank."""
    if self.alert_log is None:
      return ""
    else:
      return self.alert_log
  
  def get_rule_id(self):
    """Return the rule_id from the database, or zero."""
    if self.rule_id is None:
      return 0
    else:
      return self.rule_id
    
  def get_src_ip(self):
    """Return the source id from the alert, or zero."""
    if self.src_ip is None:
      return "0.0.0.0"
    elif self.src_ip == "(none)":
      return "127.0.0.1"
    else:
      return self.src_ip
    
  def get_user(self):
    """Return the user acccount string from the alert (potentially '(none)')"""
    if self.user is None:
      return ""
    else:
      return self.user
    
  def get_message(self):
    """Return the actual body of the log that produced the alert."""
    if self.message is None:
      return ""
    else:
      return self.message
    
  # Process a line from the OSSEC log
  # Example OSSEC Log Entry:
  # ------------------------
  # ** Alert 1297702559.16083181: - apache,
  # 2011 Feb 14 11:55:59 (www.sas.upenn.edu) 128.91.55.19->/var/log/httpd/error_log
  # Rule: 31410 (level 3) -> 'PHP Warning message.'
  # Src IP: 128.91.34.6
  # User: (none)
  # [Mon Feb 14 11:56:00 2011] [error] [client 128.91.34.6] PHP Warning:  Call-time pass-by-reference has been deprecated - argument passed by value;  If you would like to pass it by reference, modify the declaration of task_send_extra_email().  If you would like to enable call-time pass-by-reference, you can set allow_call_time_pass_reference to true in your INI file.  However, future versions may not support this any longer.  in /www/data/drupal-6.19/sites/oni.sas.upenn.edu.taskmgr/modules/task/task.module on line 254, referer: https://oni.sas.upenn.edu/taskmgr/
  # 
  def process(self, line):
    """Process a line from the OSSEC log and parse it appropriately."""
    if line[0:8] == '** Alert':
      # Got the alert line
      alert_id = line.split(' ')[2][0:-1]
      self.set_ossec_alert_id(alert_id)
    elif re.match("\d{4} [A-Z][a-z]{2} \d{1,2} ", line):
      if self.alert_log is None:
        linesplit = line.split(' ')
        self.set_date(' '.join([linesplit[0], linesplit[1], linesplit[2], linesplit[3]]))
        self.set_alert_log(' '.join(linesplit[4:]))
    elif line[0:6] == 'Rule: ':
      if self.set_rule_id(line.split(' ')[1]) == False:
        self.set_new_rule(line)
    elif line[0:8] == 'Src IP: ':
        self.set_src_ip(line[8:])
    elif line[0:6] == 'User: ':
        self.set_user(line[6:])
    else:
      # This must be the full message
      if len(line) > 1:
        self.set_message(line)
    
  def set_alert_log(self, log):
    """Set the internal alert_log variable."""
    self.alert_log = str(log).strip()
    
  def set_date(self, date):
    """Set the internal date string."""
    self.date = str(date).strip()
    
  def set_host_id(self, id):
    """Set the internal host_id integer from the database."""
    self.host_id = int(id)
    
  def set_message(self, message):
    """Set the internal message string corresponding to the OSSEC client log entry."""
    self.message = str(message).strip()
    
  # Rule: 31410 (level 3) -> 'PHP Warning message.'
  def set_new_rule(self, rulestr):
    """Set the rule_id from the database, or addd a new rule to ossec_rules."""
    rulestr = str(rulestr).strip()
    rulesplit = rulestr.split(' ')
    number = rulesplit[1]
    message = rulestr.split('->')[1][2:-1]
    level = rulesplit[3][0:-1]
    try:
      cursor = self.conn.cursor()
      sql = 'insert into ossec_rules set '
      sql += ' rule_number = "%s", '
      sql += ' rule_message = "%s", '
      sql += ' rule_level = "%s"'
      cursor.execute(sql % (number, message, level)) 
      self.conn.commit() 
      cursor.close()
      if self.set_rule_id(number) == False:
        print "Error setting new rule id in LogEntry object!"
        return False
      return True
    except Exception as err:
      syslog.syslog("There was an issue saving a new rule: ", err)
      # print "Transaction error saving new rule (set_new_rule()) in LogEntry object " , err
      return False
    
  # OSSEC alerts identifiers in the form 1297702559.16083181
  def set_ossec_alert_id(self, id):
    """Set the sanitized OSSEC alert id (ex. 1297702559.16083181)"""
    id = re.sub('![\d\.]', '', id)
    self.ossec_alert_id = id.strip()
     
  # Expects the rule number from OSSEC, rather than the db
  # therefore we have to look it up in the db and set it 
  # accordingly
  #
  # Return False if we can't find it so it can be inserted
  def set_rule_id(self, id):
    """Set the rule_id based on the OSSEC rule number.
    Return false if there is an issue with the insert.
    """
    id = int(id)
    try:
      cursor = self.conn.cursor()
      sql = 'select rule_id from ossec_rules where rule_number = %d'
      cursor.execute(sql % id) 
      rule_id = int(cursor.fetchone()[0])
    except Exception as err:
      # this error output is useless, always prints out: 'NoneType' object is unsubscriptable
      # print "Transaction error in set_rule_id() in LogEntry object:" , err
      return False
    if rule_id < 1:
      return False
    self.rule_id = rule_id
    return True
    
  def set_src_ip(self, ip):
    """Format and set the internal attribute for the alert source IP address."""
    ip= str(ip).strip()
    ip = re.sub('![\d\.]', '', ip)
    if ip == '':
      ip = '0.0.0.0'
    self.src_ip = ip
    
  def set_user(self, user):
    """Set the internal attribute for the user string from the alert."""
    self.user = str(user).strip()
    
  def save(self):
    """Persist the complete record back to the database."""
    try:
      cursor = self.conn.cursor()
      sql = 'insert into ossec_alerts set '
      sql += ' alert_date = STR_TO_DATE("%s",\'%%Y %%b %%d %%H:%%i:%%s\'), ' # 2011 Feb 14 11:55:59
      sql += ' host_id = "%s", '
      sql += ' alert_log = "%s", '
      sql += ' rule_id = "%s", '
      sql += ' rule_user = "%s", '
      sql += ' rule_log = "%s", '
      sql += ' rule_src_ip = "%s", '
      sql += ' rule_src_ip_numeric = INET_ATON("%s"), '
      sql += ' alert_ossec_id = "%s" '
      cursor.execute(sql % (self.get_date(),
                            self.get_host_id(),
                            self.get_message(),
                            self.get_rule_id(),
                            self.get_user(),
                            self.get_alert_log(),
                            self.get_src_ip(),
                            self.get_src_ip(),
                            self.get_ossec_alert_id()))
      self.conn.commit() 
      cursor.close()
    except Exception as err:
      syslog.syslog("There was an issue saving an OSSEC alert: ", err)
      # print "Transaction error saving LogEntry object " , err


import unittest

class TestLogEntry(unittest.TestCase):
  """Unit tests for the LogEntry class."""
  def setUp(self):
    """Establish the database connection and process a series of lines
    that are equivalent to a full OSSEC log entry.
    """
    try:
      self.conn = MySQLdb.connect(host=HOST,
                                  user=USERNAME,
                                  passwd=PASSWORD,
                                  db=DB,
                                  port=PORT)
    except Exception as err:
      print "Error connecting to the database" , err
      
    self.log = LogEntry(self.conn)
    self.log.process("** Alert 1297702559.16083181: - apache,")
    self.log.process("2011 Feb 14 11:55:59 (www.sas.upenn.edu) 128.91.55.19->/var/log/httpd/error_log")
    self.log.process("Rule: 31410 (level 3) -> 'PHP Warning message.'")
    self.log.process("Src IP: 128.91.34.6")
    self.log.process("User: (none)")
    self.log.process("[Mon Feb 14 11:56:00 2011] [error] [client 128.91.34.6] PHP Warning:  Call-time pass-by-reference has been deprecated - argument passed by value;  If you would like to pass it by reference, modify the declaration of task_send_extra_email().  If you would like to enable call-time pass-by-reference, you can set allow_call_time_pass_reference to true in your INI file.  However, future versions may not support this any longer.  in /www/data/drupal-6.19/sites/oni.sas.upenn.edu.taskmgr/modules/task/task.module on line 254, referer: https://oni.sas.upenn.edu/taskmgr/")
    
  def test_ossec_alert_id(self):
    """ Test the alert_id set by OSSEC."""
    self.assertEqual(self.log.get_ossec_alert_id(), "1297702559.16083181")
  def test_get_date(self):
    """Test the date parsing from the alert."""
    self.assertEqual(self.log.get_date(), "2011 Feb 14 11:55:59")
  def test_get_host_id(self):
    """Test the host_id setting and getting, artificially pinned as '1'."""
    self.log.set_host_id(1)
    self.assertEqual(self.log.get_host_id(), 1)
  def test_get_alert_log(self):
    """Test the parsing for the logfile that generated the alert."""
    self.assertEqual(self.log.get_alert_log(), "(www.sas.upenn.edu) 128.91.55.19->/var/log/httpd/error_log")
  def test_get_rule_id(self):
    """Test the rule_id persistence using a SQL query."""
    cursor = self.conn.cursor()
    sql = 'select rule_id from ossec_rules where rule_level = "3" '
    sql += 'AND rule_message = "PHP Warning message." AND rule_number = "31410"'
    cursor.execute(sql) 
    rule_id = cursor.fetchone()[0]
    cursor.close()
    self.assertEqual(self.log.get_rule_id(), rule_id)
  def test_get_src_ip(self):
    """Test the alert source IP parsing."""
    self.assertEqual(self.log.get_src_ip(), "128.91.34.6")
  def test_get_user(self):
    self.assertEqual(self.log.get_user(), "(none)")
  def test_get_message(self):
    self.assertEqual(self.log.get_message(), "[Mon Feb 14 11:56:00 2011] [error] [client 128.91.34.6] PHP Warning:  Call-time pass-by-reference has been deprecated - argument passed by value;  If you would like to pass it by reference, modify the declaration of task_send_extra_email().  If you would like to enable call-time pass-by-reference, you can set allow_call_time_pass_reference to true in your INI file.  However, future versions may not support this any longer.  in /www/data/drupal-6.19/sites/oni.sas.upenn.edu.taskmgr/modules/task/task.module on line 254, referer: https://oni.sas.upenn.edu/taskmgr/")

import sys, os, time, atexit
from signal import SIGTERM
 
class Daemon:
        """
        A generic daemon class from http://www.jejik.com/articles/2007/02/a_simple_unix_linux_daemon_in_python/
       
        Usage: subclass the Daemon class and override the run() method
        """
        def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
                self.stdin = stdin
                self.stdout = stdout
                self.stderr = stderr
                self.pidfile = pidfile
       
        def daemonize(self):
                """
                do the UNIX double-fork magic, see Stevens' "Advanced
                Programming in the UNIX Environment" for details (ISBN 0201563177)
                http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
                """
                try:
                        pid = os.fork()
                        if pid > 0:
                                # exit first parent
                                sys.exit(0)
                except OSError, e:
                        sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
                        syslog.syslog("fork #1 in Daemon failed: %d (%s)" % (e.errno, e.strerror))
                        sys.exit(1)
       
                # decouple from parent environment
                os.chdir("/")
                os.setsid()
                os.umask(0)
       
                # do second fork
                try:
                        pid = os.fork()
                        if pid > 0:
                                # exit from second parent
                                sys.exit(0)
                except OSError, e:
                        sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
                        syslog.syslog("fork #2 in Daemon failed: %d (%s)" % (e.errno, e.strerror))
                        sys.exit(1)
       
                # redirect standard file descriptors
                sys.stdout.flush()
                sys.stderr.flush()
                si = file(self.stdin, 'r')
                so = file(self.stdout, 'a+')
                se = file(self.stderr, 'a+', 0)
                os.dup2(si.fileno(), sys.stdin.fileno())
                os.dup2(so.fileno(), sys.stdout.fileno())
                os.dup2(se.fileno(), sys.stderr.fileno())
       
                # write pidfile
                os.umask(077)
                atexit.register(self.delpid)
                pid = str(os.getpid())
                file(self.pidfile,'w+').write("%s\n" % pid)
       
        def delpid(self):
                os.remove(self.pidfile)
 
        def start(self):
                """
                Start the daemon
                """
                # Check for a pidfile to see if the daemon already runs
                try:
                        pf = file(self.pidfile,'r')
                        pid = int(pf.read().strip())
                        pf.close()
                except IOError:
                        pid = None
       
                if pid:
                        message = "pidfile %s already exist. Daemon already running?\n"
                        syslog.syslog("pidfile %s already exist. Daemon already running?" % self.pidfile)
                        sys.stderr.write(message % self.pidfile)
                        sys.exit(1)
               
                # Start the daemon
                self.daemonize()
                self.run()
 
        def stop(self):
                """
                Stop the daemon
                """
                # Get the pid from the pidfile
                try:
                        pf = file(self.pidfile,'r')
                        pid = int(pf.read().strip())
                        pf.close()
                except IOError:
                        pid = None
       
                if not pid:
                        message = "pidfile %s does not exist. Daemon not running?\n"
                        syslog.syslog("pidfile %s does not exist. Daemon not running?" % self.pidfile)
                        sys.stderr.write(message % self.pidfile)
                        return # not an error in a restart
 
                # Try killing the daemon process       
                try:
                        while 1:
                                os.kill(pid, SIGTERM)
                                time.sleep(0.1)
                except OSError, err:
                        err = str(err)
                        if err.find("No such process") > 0:
                                if os.path.exists(self.pidfile):
                                        os.remove(self.pidfile)
                        else:
                                print str(err)
                                sys.exit(1)
 
        def restart(self):
                """
                Restart the daemon
                """
                self.stop()
                self.start()
 
        def run(self):
                """
                Nothing to see here, move along. Move along.
                """

class OSSECLogParser(Daemon):
  """This is the log watching object that tails the ossec alert file
  and writes entries into the database.
  """

  def follow(self, thefile):
    """Tail (follow) the log file and parse it into the database."""
    thefile.seek(0,2)      # Go to the end of the file
    sleep = 0.00001
    while True:
      line = thefile.readline()
      if not line:
        time.sleep(sleep)    # Sleep briefly
        if sleep < 1.0:
          sleep += 0.00001
        continue
      sleep = 0.00001
      yield line
  def run(self):
    """Start the process, extended from Daemon."""
    while True:
      self.do_log()
      #time.sleep(1)
  def do_log(self):
    """Connect to the database and watch the logfile."""
    try:
      conn = MySQLdb.connect(host=HOST,
                                  user=USERNAME,
                                  passwd=PASSWORD,
                                  db=DB,
                                  port=PORT)
    except Exception as err:
      syslog.syslog("Error connecting to the database: " , err)
      print "Error connecting to the database" , err
    logfile = open("/var/ossec/logs/alerts/alerts.log")
    loglines = self.follow(logfile)
    log = LogEntry(conn)
    for line in loglines:
      # start a new log if necessary
      if line[0:8] == '** Alert':
        if log.get_ossec_alert_id() is not "":
          print log.get_alert_log()
          print log.get_date()
          print log.get_host_id()
          print log.get_message()
          print log.get_ossec_alert_id()
          print log.get_rule_id()
          print log.get_src_ip()
          print log.get_user()
          log.save()
        log.clear()
      log.process(line)
          
if __name__ == '__main__':
  daemon = OSSECLogParser('/tmp/hector-ossec-mysql.pid')
  if len(sys.argv) == 2:
    if 'start' == sys.argv[1]:
      daemon.start()
    elif 'stop' == sys.argv[1]:
      daemon.stop()
    elif 'restart' == sys.argv[1]:
      daemon.restart()
    elif 'test' == sys.argv[1]:
      suite = unittest.TestLoader().loadTestsFromTestCase(TestLogEntry)
      unittest.TextTestRunner(verbosity=2).run(suite)
    else:
      print "Unknown command"
      sys.exit(2)
    sys.exit(0)
  else:
    print "usage: %s start|stop|restart|test" % sys.argv[0]
    sys.exit(2)

    