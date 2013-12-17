<?php
/**
* This is the generic subcontroller for modifying objects.
* The file expects a GET id element and a POST array that
* matches up to the object specified.
* 
* @package HECTOR
* @author Justin C. Klein Keane <jukeane@sas.upenn.edu>
**/

if (! isset($_GET['object'])) {
	// in case we don't have the right input
	$template = 'default';
}
else {
	$object = ucfirst(urldecode($_GET['object']));	
	$file = $approot . 'lib/class.' . $object . '.php';
	if (is_file($file)) {
		/**
		 * Include the source file for the class we want to modify
		 */
		include_once($file);
		$id = isset($_GET['id']) ? intval($_GET['id']) : '';
		$generic = new $object($id);
		$post_values = $generic->get_add_alter_form();
		foreach ($post_values as $val) {
			//strip off any post array demarkers 
			if (substr($val['name'],-2)=='[]') $val['name'] = substr($val['name'], 0, -2);
			$generic->process_form($val['process_callback'], $_POST[$val['name']]);
		}
		$generic->save();
	}
	$message = 'Record ';
	$message .=  ($id == '') ? 'created' : 'updated';
}
$updated = 'yes';

if (! isset($_GET['ajax'])) include_once($templates. 'admin_headers.tpl.php');
if (isset($template) && $template == 'default') {
	include_once($templates . 'default.tpl.php');
}
else {	
	$_GET['action'] = 'details';
	include_once($approot . 'actions/details.php');
}
?>