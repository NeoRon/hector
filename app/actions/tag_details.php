<?php 
/**
 * Subcontroller to gather details for a specific tag
 * 
 * @package Hector
 * @author Ubani A Balogun
 * @version 2014.08.07
 */

require_once($approot . 'lib/class.Db.php');
include_once($approot . 'lib/class.Tag.php');
include_once($approot . 'lib/class.Incident.php');
include_once($approot . 'lib/class.Article.php');

// screenshots.css
$css = '';
$css .= "<link href='css/jquery.dataTables.css' rel='stylesheet'>\n";

// javascripts
$javascripts = '';
$javascripts .= "<script type='text/javascript' src='js/jquery.dataTables.min.js'></script>\n";
$javascripts .= "<script type='text/javascript' src='js/tag_details.js'></script>\n";

$id = isset($_GET['id']) ? intval($_GET['id']) : 0;
$tag = new Tag($id);
$tag_name = $tag->get_name();

$incident_ids = $tag->get_incident_ids();
$incidents = array();

if (isset($incident_ids[0])){
	foreach ($incident_ids as $incident_id){
		$incident = new Incident($incident_id);
		$incidents[] = $incident->get_object_as_array();
	}
}

$article_ids = $tag->get_article_ids();
$articles = array();
if (isset($article_ids[0])){
	foreach ($article_ids as $article_id){
		$article = new Article($article_id);
		$articles[] = $article->get_object_as_array();
	}
}




include_once($templates. 'admin_headers.tpl.php');
include_once($templates . 'tag_details.tpl.php');

?>