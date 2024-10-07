PANORAMA = {
	'command': 'rename',
	'allow_subgroups': False,
	'format': '{directory:s}/{base:s}{alphacounter:s}{extension:s}',
	'basepattern': r'^(?P<base>.*?)\s*[0-9]*$',
	'counter': 0,
	'tag': 'Panorama'
}
HDR = {
	'command': 'rename',
	'allow_subgroups': False,
	'format': '{directory:s}/{base:s}{alphacounter:s}{extension:s}',
	'basepattern': r'^(?P<base>.*?)\s*[0-9]*$',
	'counter': 0,
	'tag': 'HDR'
}
GROUP = {
	'command': 'rename',
	'allow_subgroups': True,
	'format': "{directory:s}/{base:s} {counter:03d}{extension:s}",
	'basepattern': r'^(?P<base>.*?)\s*[0-9]*$',
	'counter': 1
}
DATE = {
	'command': 'rename',
	'allow_subgroups': True,
	'format': "{directory:s}/{datetime:s} {base:s}{extension:s}",
	'basepattern': r'^([0-9]{2,4}\.?[0-9]{2}\.?[0-9]{2}[\s_]?[0-9]{2}[h:]?[0-9]{2}[m:]?[0-9]{2}s?|[0-9]*)\s*(?P<base>.*?)\s*[0-9]*$',
	'counter': 1
}
POSTPROCESS = {
	'command': 'postprocess',
	'allow_subgroups': True,
	'basepattern': r'^(?P<base>.*?)\s*[0-9]*$',
	'recursive': True
}
