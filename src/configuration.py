# Copyright 2020 Scott Maday
# 
# This module builds and loads a configuration for use in all aspects of the rest of the program.
# Every GUI, every plugin, and every built-in uses the configuration in one way or another to load, save, and share hierarchical data.
# It was kind of over-engineered but the Configuration is designed for use with a structure that helps data loaded from a JSON file
# to be aware of defaults, ranges, options, and any other attributes defined in the structure file.

import sys, os.path, json, logging
from shutil import copyfile
from xml.etree import ElementTree

if sys.version_info[0] >= 3:
	unicode = str


class Stuctural_Type(object):
	def __init__(self, type_name, func_cast, func_validate = None):
		self.type_name = type_name
		self.func_cast = func_cast
		self.func_validate = func_validate if func_validate else lambda: None

def validate_number(type, x, attribs):
	x_num = 0
	castor = int if type == "int" else float
	try:
		x_num = castor(x)
	except ValueError:
		return False
	if "min" in attribs and x_num < castor(attribs["min"]):
		return False
	if "max" in attribs and x_num > castor(attribs["max"]):
		return False
	return True

def validate_string(x, attribs):
	if "min" in attribs and len(x) < int(attribs["min"]):
		return False
	if "max" in attribs and len(x) > int(attribs["max"]):
		return False
	if "options" in attribs:
		options = attribs["options"].split(SCHEMA_OPTION_DELIMITER)
		if not x in options:
			return False
	return not x.isspace()

def get_structural_type(type_name):
	for struct_type in CONFIGURATION_STRUCTURAL_TYPES:
		if struct_type.type_name == type_name:
			return struct_type
	return None

CONFIGURATION_STRUCTURAL_TYPES	= [
	Stuctural_Type("bool", lambda x=None: str(x).lower() in ["true", "1"] if x else bool(), lambda x, attribs: str(x).lower() in ["true", "1", "false", "0"]),
	Stuctural_Type("int", int, lambda x, attribs: validate_number("int", x, attribs) ),
	Stuctural_Type("float", float, lambda x, attribs: validate_number("float", x, attribs) ),
	Stuctural_Type("string", str, validate_string),
	Stuctural_Type("file", str, lambda x, attribs: validate_string(x, attribs) and os.path.isfile(x)),
	Stuctural_Type("directory", str, lambda x, attribs: validate_string(x, attribs) and os.path.isdir(x))
]
CONFIGURATION_APPLY_IMPLICIT_PROPERTIES			= False
CONFIGURATION_STRUCTURE_OBJECT_CONTEXT_LABEL	= "name"

SCHEMA_OPTION_DELIMITER						= ","
SCHEMA_NULL_KEYWORDS_ENABLED				= True
SCHEMA_NULL_KEYWORDS						= ["null", "none"]
SCHEMA_STRUCTURE_OBJECT_CONTEXT_ATTRIBUTES	= True				# gives context to attributes in objects in structural arrays
SCHEMA_STRUCTURE_OBJECT_CONTEXT_NAME		= "_schema_name"
	
################################ [ START OF MAIN CODE ]	################################


# A tree that represents the configuration structure of objects in the schema
class Structure_Object(object):
	__logger = logging.getLogger(__name__)
	
	def __init__(self, name = None, label = None, attributes = None):
		self.name = name
		self.label = label if label else name
		self.attributes = attributes if isinstance(attributes, dict) else {}
		self.tree = []
		self.is_array = False
		
	def get_num_copies(self):
		if not self.is_array:	# non-array objects cannot have copies
			return None
		if not "copies" in self.attributes:
			return 0
		return int(self.attributes["copies"])
	
	def append(self, struct):
		if struct == None:
			return None
		assert isinstance(struct, (Structure_Object, Structure_Property))
		self.tree.append(struct)
	
	def __contains__(self, key):
		for struct in self.tree:
			if struct.name == key:
				return True
		return False
	
	def __getitem__(self, key):
		if isinstance(key, (Structure_Object, Structure_Property)):
			key = key.name
		for struct in self.tree:
			if struct.name == key:
				return struct
	
	def __iter__(self):
		return self.tree.__iter__()
		
	def __repr__(self):
		return "%s: %s, #%d nodes" % (type(self).__name__, self.name if self.name else self.label, len(self.tree))
	
	def __str__(self):
		tag = "array" if self.is_array else "object"
		tree_repr = ", ".join([repr(x) for x in self.tree])
		if self.name:
			return "<%s name='%s'>%s</%s>" % (tag, str(self.name), tree_repr, tag)
		else:
			return "<%s>%s</%s>" % (tag, tree_repr, tag)
###

# Represents the configuration structure based on the schema
# This is the base class for all structured items and functions to encaptulate other structures
class Structure_Property(object):
	__logger = logging.getLogger(__name__)
	
	def __init__(self, struct_type, name = None, label = None, default = None, attributes = None):
		self.struct_type = struct_type
		assert isinstance(struct_type, Stuctural_Type)
		self.name = name
		self.label = label if label else name
		self.default = (self.cast_value(default) if default != None else self.struct_type.func_cast()) if not SCHEMA_NULL_KEYWORDS_ENABLED or str(default).lower() not in SCHEMA_NULL_KEYWORDS else None
		self.attributes = attributes if isinstance(attributes, dict) else {}
	
	def get_options(self):
		if not "options" in self.attributes:
			return None
		options = self.attributes["options"].split(SCHEMA_OPTION_DELIMITER)
		if self.struct_type.type_name != "string":	# no need to waste time casting things that are already strings
			for i, option in enumerate(options):
				options[i] = self.struct_type.func_cast(option)
		return options
	
	def validate_value(self, value):
		return self.struct_type.func_validate(value, self.attributes)
		
	def cast_value(self, value):
		if SCHEMA_NULL_KEYWORDS_ENABLED and str(value).lower() in SCHEMA_NULL_KEYWORDS:
			return None
		return self.struct_type.func_cast(value)
	
	def is_implicit(self):
		return "presentation" in self.attributes and self.attributes["presentation"] == "implicit"
	
	def __repr__(self):
		return "%s(%s): %s=%s" % (type(self).__name__, self.struct_type.type_name, self.name, self.default)
		
	def __str__(self):
		return "<%s>%s</%s>" % (self.struct_type.type_name, str(self.default), self.struct_type.type_name)
###


# The actual configurable data as either a dict or list
# The content is a list of either: native types or Configurations
class Configuration(object):
	__logger = logging.getLogger(__name__)
	
	def __init__(self, param = None):
		self._content = {}
		self.struct = None
		
		if issubclass(type(param), Configuration):
			self.struct = param.struct
			self.build_structure()
			self._content = param._content
		elif isinstance(param, Structure_Object):
			self.struct = param
			self.build_structure()
	
	# Loads the default ideal data into the content defined by the Structure
	# It's very important that must be called before any data is set
	def build_structure(self):
		assert isinstance(self.struct, Structure_Object)
		num_copies = 1
		if self.struct.is_array:
			self._content = []
			num_copies = self.struct.get_num_copies()
		else:
			self._content = {}
		if num_copies == 0:
			return None
		
		for i in range(num_copies):	# almost certainly the laziest way to do this but oh well
			for sub_struct in self.struct:
				if isinstance(sub_struct, Structure_Property):
					self.set_or_append(sub_struct.default, sub_struct.name)
				elif isinstance(sub_struct, Structure_Object):
					sub_config = Configuration(sub_struct)
					if SCHEMA_STRUCTURE_OBJECT_CONTEXT_ATTRIBUTES:
						if self.struct.is_array and not sub_struct.is_array and sub_struct.name:
							sub_config[SCHEMA_STRUCTURE_OBJECT_CONTEXT_NAME] = sub_struct.name
					self.set_or_append(sub_config, sub_struct.name)
	
	# Sets data from a JSON file
	def set_data(self, data):
		assert isinstance(data, (dict, list))
		# Reformat content in preference of the data if no structure is given
		if not self.struct:
			self._content = {} if isinstance(data, dict) else []
		
		# Place the data into content as a configuration
		if isinstance(self._content, dict) and isinstance(data, dict):
			for key, sub_data in data.items():
				if not isinstance(sub_data, (dict, list)):		# easiest way to control data flow
					if key == CONFIGURATION_STRUCTURE_OBJECT_CONTEXT_LABEL and self.struct and sub_data:
						self.struct.label = sub_data
						self[key] = str(sub_data)
					elif isinstance(sub_data, unicode):			# easiest way to correct json loader behavior
						self[key] = str(sub_data)
					else:
						self[key] = sub_data
				else:
					if not key in self:
						self[key] = Configuration(None if not self.struct or not key in self.struct else self.struct[key])
					self[key].set_data(sub_data)
		# Lists will try to be smart about what Structure gets assigned to which object
		elif isinstance(self._content, list) and isinstance(data, list):
			self._content = []	# why did i waste my time writing what's below when this is way better and works when objects get removed?
			"""content_len = len(self._content)
			data_len = len(data)
			if data_len > content_len:
				self._content.extend([None]*(data_len - content_len))							# extend for the difference between data that's already there and data that will be added
				self.__logger.debug("Had to resize content from %d to data length %d in Configuration", content_len, data_len)"""
			for i, sub_data in enumerate(data):
				sub_struct = None
				if self.struct:
					if SCHEMA_STRUCTURE_OBJECT_CONTEXT_NAME in sub_data and isinstance(sub_data, dict):
						sub_struct = self.struct[sub_data[SCHEMA_STRUCTURE_OBJECT_CONTEXT_NAME]]	# give structure to objects who claim they have it
				sub_config = Configuration(sub_struct)
				if isinstance(sub_data, (dict, list)):
					sub_config.set_data(sub_data)
				# self._content[i] = sub_config
				self._content.append(sub_config)
			
	
	# Casts to object to be written as a JSON
	def as_obj(self):
		obj = {}
		if isinstance(self._content, dict):
			for key, sub_data in self._content.items():
				if CONFIGURATION_APPLY_IMPLICIT_PROPERTIES or not (isinstance(self.struct, Structure_Object) and key in self.struct and self.struct[key].is_implicit() and sub_data == self.struct[key].default):
					obj[key] = sub_data
				if isinstance(sub_data, Configuration):
					obj[key] = sub_data.as_obj()
		elif isinstance(self._content, list):
			obj = []
			for sub_data in self._content:
				if sub_data != None:
					obj.append(sub_data)
				if isinstance(sub_data, Configuration):
					obj.append(sub_data.as_obj())
		return obj
	
	# Returns the set of all allowed configurations for a structural array (an array in a schema that is only defined to show its structure)
	# NOTE: False returns are an empty array [] and NOT None
	def get_structural_array_configurations(self, warning = True):
		if not self.struct or not self.struct.is_array:
			if warning:
				self.__logger.warning("Cannot get structural array object since this configuration is not a structural array: %s", repr(self))
			return []
		structural_array_configs = []
		for sub_struct in self.struct:
			if isinstance(sub_struct, Structure_Object):
				config = Configuration(sub_struct)
				if SCHEMA_STRUCTURE_OBJECT_CONTEXT_ATTRIBUTES:
					config.set_or_append(sub_struct.name, SCHEMA_STRUCTURE_OBJECT_CONTEXT_NAME)
				structural_array_configs.append(config)
		return structural_array_configs
	
	def get_name(self):
		return self.struct.name if self.struct and self.struct.name else type(self).__name__
	
	def is_list(self):
		return isinstance(self._content, list)
	
	def set_or_append(self, value, key = None):
		if isinstance(self._content, dict):
			self[key] = value
		elif isinstance(self._content, list):
			self.append(value)
		return self
		
	def append(self, value):
		if not isinstance(self._content, list):
			return None
		self._content.append(value)
	
	def remove(self, value, key = None):
		if isinstance(self._content, dict):
			self._content.pop(key)
		elif isinstance(self._content, list):
			self._content.remove(value)
		return self
	
	def items(self):
		if isinstance(self._content, dict):
			return self._content.items()
		elif isinstance(self._content, list):
			return enumerate(self._content)
			
	def __contains__(self, key):
		return (isinstance(self._content, dict) and key in self._content) or (isinstance(self._content, list) and isinstance(key, list) and 0 <= key < len(self._content))
	
	def __getitem__(self, key):
		if isinstance(self._content, dict) and key != None and key in self._content:
			return self._content[key]
		elif isinstance(self._content, list) and isinstance(key, int) and 0 <= key < len(self._content):
			return self._content[key]
		return None
		
	def __setitem__(self, key, value):
		if not isinstance(self._content, dict):
			return None
		self._content[key] = value
	
	def __str__(self):
		return self[CONFIGURATION_STRUCTURE_OBJECT_CONTEXT_LABEL] if isinstance(self._content, dict) and CONFIGURATION_STRUCTURE_OBJECT_CONTEXT_LABEL in self and isinstance(self[CONFIGURATION_STRUCTURE_OBJECT_CONTEXT_LABEL], str) else (self.struct.label if self.struct and self.struct.label else (self.get_name()))
	
	def __repr__(self):
		return repr(self._content)
###

# Configuration root node
class Root_Configuration(Configuration):
	__logger = logging.getLogger(__name__)
	
	def __init__(self, file_name, param = None):
		super(Root_Configuration, self).__init__(param)
		if issubclass(type(param), Root_Configuration):
			self.file_name = param.file_name
		else:
			self.file_name = file_name
	
	def save(self):
		backup_name = self.file_name + ".bak"
		if os.path.isfile(self.file_name) and not os.path.exists(backup_name):
			try:
				copyfile(self.file_name, backup_name)
				self.__logger.info("Backup '%s' created for configuration", backup_name)
			except Exception:
				self.__logger.exception("Exception raised while trying to backup for configuration: %s", self.file_name)
		with open(self.file_name, "w") as file:
			json.dump(self.as_obj(), file, indent=4)
	
	def get_name(self):
		return os.path.splitext(os.path.basename(self.file_name))[0] # if not self.struct or not self.struct.label else self.struct.label
	

################################ [ STATIC METHODS ]	################################

config_logger = logging.getLogger(__name__)

def structure_from_xml(elem):
	assert isinstance(elem, ElementTree.Element) and (any(elem.tag == x.type_name for x in CONFIGURATION_STRUCTURAL_TYPES) or elem.tag in ["object", "array"])
	
	name = None
	label = None
	if "name" in elem.attrib:
		name = elem.attrib["name"]
		del elem.attrib["name"]
	if "label" in elem.attrib:
		label = elem.attrib["label"]
		del elem.attrib["label"]
	
	if elem.tag == "object" or elem.tag == "array":
		struct_obj = Structure_Object(name, label, elem.attrib)
		struct_obj.is_array = elem.tag == "array"
		for sub_elem in elem:
			struct_obj.append(structure_from_xml(sub_elem))
		return struct_obj
	else:
		struct_type = None
		for x in CONFIGURATION_STRUCTURAL_TYPES:
			if elem.tag == x.type_name:
				struct_type = x
				break
		return Structure_Property(struct_type, name, label, elem.text, elem.attrib)

def configuration_from_obj(obj):
	data_type = type(obj).__name__
	if data_type == "str":
		data_type = "string"
	data = obj
	
	if data_type == "list":
		data_type = "array"
		data = []
		for sub_obj in obj:
			data.append(configuration_from_obj(sub_obj))
	elif data_type == "dict":
		data_type = "object"
		data = []
		for key, sub_obj in obj.items():
			sub_config = configuration_from_obj(sub_obj)
			sub_config.name = key
			data.append(sub_config)
	return Configuration(data_type, None, None, {}, data)

def schema_from_file(schema_file):
	if not schema_file or not os.path.isfile(schema_file):
		config_logger.warning("Schema file '%s' cannot be opened. The configuration may not behave as intended.", schema_file)
		return None
	tree_root = ElementTree.parse(schema_file)
	struct = structure_from_xml(tree_root.getroot())
	struct.attributes["file_name"] = os.path.abspath(schema_file)	# this will come in handy later
	return struct

def configuration_from_file(config_file, schema_file = None, autocreate_config = False):
	if not isinstance(config_file, str) and not isinstance(config_file, unicode):
		config_logger.error("Configuration file '%s' is invalid", str(config_file))
		return None
	config_obj = {}
	struct = None
	
	if os.path.isfile(config_file):
		with open(config_file) as config_f:
			config_obj = json.load(config_f)
		config_logger.debug("Successfully loaded configuration %s", config_file)
	struct = schema_from_file(schema_file)
	config = Root_Configuration(config_file, struct)
	config.set_data(config_obj)
	if not os.path.isfile(config_file) and autocreate_config:
		config.save()
	return config
