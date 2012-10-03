<?php

/**
 * 
 * Script for performing routine NMAP scans based on
 * specifications in the database.  
 * 
 * This script runs an NMAP scan, saving the results
 * to an XML file on the filesystem.  Once the scans
 * are complete the script parses this file into the
 * database.  This is useful for debugging, for 
 * allowing other processes to consume the NMAP scan
 * results, and for performance (the database import
 * isn't racing against the scan).
 * 
 * For full help on usage see show_help() below.  
 * Example usage:
 * 
 * $ php nmap_scan.php -a -p=80,443 -g=1,4 -e=22
 * 
 * This script is run from scan_cron.php and 
 * nmap_rescan_old.php
 * 
 * @author Justin C. Klein Keane <jukeane@sas.upenn.edu>
 * @package HECTOR
 * 
 * Last modified May 10, 2012
 */
 
/**
 * Defined vars
 */
if(php_sapi_name() == 'cli') {
	$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
	$approot = realpath(substr($_SERVER['PATH_TRANSLATED'],0,strrpos($_SERVER['PATH_TRANSLATED'],'/')) . '/../') . '/';	
}


/**
 * Neccesary includes
 */
require_once($approot . 'lib/class.Config.php');
require_once($approot . 'lib/class.Dblog.php');
require_once($approot . 'lib/class.Host.php');
require_once($approot . 'lib/class.Host_group.php');
require_once($approot . 'lib/class.Log.php');
require_once($approot . 'lib/class.Nmap_scan.php');
require_once($approot . 'lib/class.Nmap_scan_result.php');
require_once($approot . 'lib/class.Scan_type.php');
	
// Make sure of the environment
global $add_edit;
if(php_sapi_name() != 'cli') {
	$hostgroups = new Collection('Host_group');
	$grouplist = "";
	foreach ($hostgroups->members as $group) {
		//$grouplist += $group->get_name();
	}
	$alert = '';
	$portlist = '';
	$exclusionlist = '';
	$version = '';
	if (isset($_GET['id'])) {
		$id = intval($_GET['id']);
		$scan = new Scan_type($id);
		$flags = $scan->get_flags();
		$flags = explode('-', $flags);
		foreach ($flags as $flag) {
			switch (substr($flag, 0,1)) {
				case 'a': 
					$alert = 'checked=\'checked\'';
					break;
				case 'p':
					$portlist = substr($flag, 2);
					break;
				case 'e':
					$exclusionlist = substr($flag, 2);
					break;
				case 'v': 
					$version = 'checked=\'checked\'';
					break;
			}
		}
	}
	
	$is_executable[] = array('nmap_scan.php' => 'NMAP scan');
	global $javascripts;
	$javascripts[] = <<<EOT
	<script type="text/javascript">
		// Make this scan the default
		document.getElementById("nmap_scan.php").defaultSelected = true;
		function nmap_scan_display() {
			var nmapHTML = "Alert on Changes: <input id='add-remove-alert' type='checkbox' onClick='addRemoveAlert()' $alert/><br/>";
			nmapHTML += "Ports to scan (comma delimited): <input type='text' id='portlist' onBlur='updatePorts()' value='$portlist'/><br/>";
			nmapHTML += "Only scan hosts with these ports open (comma delimited): <input type='text' id='oportlist' onBlur='updateoPorts()' value='$exclusionlist'/><br/>";
			nmapHTML += "Attept version detection: <input id='add-remove-version' type='checkbox' onClick='addRemoveVersion()' $version/><br/>";
			document.getElementById("specs").innerHTML = nmapHTML;
		}
		// Fire this up as it's the default
		nmap_scan_display();
		function addRemoveAlert() {
			if (document.getElementById("add-remove-alert").checked == true) {
				if (! document.getElementById("flags").value.match(/-a/g)) {
					document.getElementById("flags").value += " -a ";
				}
			}
			else {
				document.getElementById("flags").value = document.getElementById("flags").value.replace("-a", "");
			}
		}
		function addRemoveVersion() {
			if (document.getElementById("add-remove-version").checked == true) {
				if (! document.getElementById("flags").value.match(/-v/g)) {
					document.getElementById("flags").value += " -v ";
				}
			}
			else {
				document.getElementById("flags").value = document.getElementById("flags").value.replace("-v", "");
			}
		}
		function updatePorts() {
			// First format the input properly
			document.getElementById("portlist").value = document.getElementById("portlist").value.replace(/[^\d^\,]*/g, '');
			// Clear any pre-existing values
			if (document.getElementById("flags").value.match(/-p/g)) { 
				document.getElementById("flags").value = document.getElementById("flags").value.replace(/-p=[\d\,]*/g, '');
			}
			// Update the flags if necessary
			if (! document.getElementById("portlist").value == "") {
				document.getElementById("flags").value += "-p=" + document.getElementById("portlist").value;
			}
		}
		function updateoPorts() {
			// First format the input properly
			document.getElementById("oportlist").value = document.getElementById("oportlist").value.replace(/[^\d^\,]*/g, '');
			// Clear any pre-existing values
			if (document.getElementById("flags").value.match(/-e/g)) { 
				document.getElementById("flags").value = document.getElementById("flags").value.replace(/-e=[\d\,]*/g, '');
			}
			// Update the flags if necessary
			if (! document.getElementById("oportlist").value == "") {
				document.getElementById("flags").value += "-e=" + document.getElementById("oportlist").value;
			}
		}
	</script>
EOT;
	$onselects['nmap_scan.php'] = 'nmap_scan_display()';
}
else {	
	// Set high mem limit to prevent resource exhaustion
	ini_set('memory_limit', '512M');
	
	syslog(LOG_INFO, 'Nmap_scan.php starting.');
	
	$scriptrun = 1;
	
	/**
	 * Singletons
	 */
	new Config();
	$db = Db::get_instance();
	$dblog = Dblog::get_instance();
	$log = Log::get_instance();
	$nmap = $_SESSION['nmap_exec_path'];
	if (! is_executable($nmap)) {
		loggit("nmap_scan.php status", "Couldn't locate NMAP executable from config.ini, quitting.");
		die("Can't find NMAP executable at $nmap.  Check your config.ini.\n");
	}
	loggit("nmap_scan.php status", "nmap_scan.php invoked.");
	
	// Check to make sure arguments are present
	if ($argc < 2) show_help("Too few arguments!  You tried:\n " . implode(' ', $argv));
	
	// Set defaults
	$scanall = 0;
	$ports = null;
	$groups = null;
	$hasport = null;
	$alertchange = 0;
	$version = FALSE;
	$nmap_debug = TRUE;
	
	$Nmap_scan = new Nmap_scan();
	$scan_id = $Nmap_scan->get_id();
	
	/**
	 * This will be an associative array of the form
	 * host_ip => Host object
	 */
	$hosts = array();
	
	/** 
	 * Array of ints for quick reference
	 */
	$host_ids = array();
	
	/**
	 * Get the next id for this scan
	 */
	
	
	// Parse through the command line arguments
	foreach ($argv as $arg) {
		if (substr($arg, -13) == 'nmap_scan.php') continue;
		$flag = substr(strtolower($arg),0,2);
		if (($flag != '-a' && $flag != '-v') && strpos($arg,'=') === FALSE) {
			show_help("Improper argument usage in arg [$arg]");
		}
		switch ($flag) {
			case '-a':
				$alertchange = 1;
				break;
			case '-e':
				$hasport = substr($arg,strpos($arg,'=')+1);
				break;
			case '-g':
				$groups = substr($arg,strpos($arg,'=')+1);
				break;
			case '-p':
				$ports = substr($arg,strpos($arg,'=')+1);
				break;
			case '-v':
				$version = TRUE;
				break;
		}
	}
	
	// Determine host groups
	if ($groups != NULL) {
		$groups = mysql_real_escape_string($groups);
		$host_groups = new Collection('Host_group', 'AND host_group_id IN(' . $groups .')');
		if (isset($host_groups->members) && is_array($host_groups->members)) {
			foreach($host_groups->members as $host_group) {
				foreach ($host_group->get_host_ids() as $host_id) {
					$newhost = new Host($host_id);
					if ($newhost->get_ignore_portscan() < 1) {
						$hosts[$newhost->get_ip()] = $newhost;
						$host_ids[] = $newhost->get_id();
					}
				}
			}
		}
	}
	else {
		// just grab all the hosts
		$allhosts = new Collection('Host');
		if (isset($allhosts->members) && is_array($allhosts->members)) {
			foreach ($allhosts->members as $newhost) {
				if ($newhost->get_ignore_portscan() < 1) {
					$hosts[$newhost->get_ip()] = $newhost;
					$host_ids[] = $newhost->get_id();
				}
			}
		}
	}
	$filter = '';
	
	// Restrict machines based on port specifications
	if ($hasport != null) {
		$filter .= ' AND nsr.state_id=1 AND nsr.nmap_scan_result_port_number in (' . mysql_real_escape_string($hasport) . ')';
		$filter .= ' AND nsr.host_id IN (' . implode(',',$host_ids) . ')';
		$prevscan = new Collection('Nmap_scan_result', $filter);
		if (isset($prevscan->members) && is_array($prevscan->members)) {
			// rebuild the $hosts and $host_ids arrays
			$hosts = array();
			$host_ids = array();
			foreach($prevscan->members as $seenhosts) {
				if (array_search($seenhosts->get_host_id(), $host_ids) === FALSE)
				$hosts_ids[] = $seenhosts->get_host_id();
				$tmphost = new Host($seenhosts->get_host_id());
				$hosts[$tmphost->get_ip()] = $tmphost;
			}
		}
	}
	// Write IP's to a file for NMAP
	$ipfilename = $approot . 'scripts/ips.txt';
	$fp = fopen($ipfilename, 'w') or die("Couldn't open scirpts/ips.txt'");
	foreach($hosts as $host_ip => $host_object) {
		fwrite($fp, $host_ip . "\n");
	}
	fclose($fp);
	
	// Run the scan and store the results on the filesystem
	$xmloutput = $approot . 'scripts/results-' . time() . '.xml';  // Avoid namespace collissions!
	$portspec = ($ports != '') ? '-p T:' . $ports : '';
	if ($version) $portspec .= ' -sV ';
	$command = $nmap . ' -sT -PN -oX ' . $xmloutput . ' ' . $portspec .
		' -T4 -iL ' . $ipfilename;
	loggit("nmap_scan.php process", "Executing the command: " . $command);
	shell_exec($command);
	loggit("nmap_scan.php process", "The command: " . $command . " completed!");
	
	// Run the import
	system('/usr/bin/php ' . $approot . 'scripts/nmap_scan_loadfile.php ' . $scan_id . ' ' . $xmloutput);
	
	// Shut down nicely
	loggit("nmap_scan.php status", "Nmap scan complete.");
	$db->close();
	syslog(LOG_INFO, 'Nmap_scan.php complete.');
}

function show_help($error) {
	echo "Usage: nmap_scan.php [arguments=params]\n";
  echo $error;
	echo "\n\n";
	echo "Arguments:\n";
	echo "-a\tAlert if ports have changed on the host\n";
	echo "-e\tOnly scan hosts that already have specified port(s) open\n";
	echo "-g\tHost groups id's to scan\n";
	echo "-p\tLimit scan to specific ports\n";
	echo "-v\tAttempt to determine version information\n";
	echo "\n\nExample Usage:\n";
	echo '$ php nmap_scan.php -a -p=80,443 -g=1,4 -e=22 ' . "\n";
	echo "Would scan for hosts in the 'web servers' and 'critical hosts' groups (id 1 & 4) \n";
	echo "for ports 80 and 443, but only machines that have been seen with port 22 open.\n\n";
	//exit;
}

function set_state_string($state) {
	$retval = 'unknown';
	switch ($state) {
		case 1: $retval = 'open'; break;
		case 2: $retval = 'closed'; break;
		case 3: $retval = 'filtered'; break;
	}
	return $retval;
}

function loggit($status, $message) {
	global $log;
	global $dblog;
	$log->write_message($message);
	$dblog->log($status, $message);
}

?>
