## Main script for the compiler
import os
import sys
import runpy
import shutil
import logging
import traceback
import importlib
import importlib.util
from lib.util import ijoin


# Check if the dependencies are installed
def dependency_check():
	# Prepare a list of dependencies
	dependencies = [
		("numpy", "numpy"),
		("struct", "struct"),
		("hashlib", "hashlib"),
		("PIL", "pillow"),
		("traceback_with_variables", "traceback-with-variables"),
	]
	
	try:
		for (importName, packageName) in dependencies:
			importlib.import_module(importName)
	except ImportError:
		print("- The following new dependencies were not found:")
		# List the missing dependencies, one per line
		missing_dependencies = [packageName for (importName, packageName) in dependencies if not importlib.util.find_spec(importName)]
		print("-", "\n- ".join(missing_dependencies))
		print("-")
		
		print("- They will be installed now (or you can close the program now and install them manually).")
		print("- Once the installation is complete, the program will be closed automatically.")
		print("- Please run it again afterwards.")
		print("-")
		input("Press Enter to install...")
		
		print("- Installing...")
		
		# Install the dependencies (closes the program automatically after the installation)
		sys.argv = ["pip", "install"] + missing_dependencies
		runpy.run_module("pip", run_name="__main__")


def logger_init(__name__):
	# If a log file already exists, add .old to it
	LOG_NAME = "error.log"
	LOG_NAME_OLD = LOG_NAME + ".old"
	if os.path.exists(LOG_NAME):
		if os.path.exists(LOG_NAME_OLD):
			os.remove(LOG_NAME_OLD)
		os.rename(LOG_NAME, LOG_NAME_OLD)
	
	# Create a logger
	logger = logging.getLogger(__name__)
	
	# Create a file handler which will only create a file when an exception occurs
	handler = logging.FileHandler(LOG_NAME, delay=True)
	
	# Create a formatter and add it to the handler
	formatter = logging.Formatter('%(asctime)-15s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)
	
	# Add the handler to the logger
	logger.addHandler(handler)
	return logger


def run_type_request(argv):
	if len(argv) > 1 and argv[1] in ["1", "0"]:
		return argv[1]
	
	print("Usage:")
	print("  compiler_main <run type>")
	print("run type:")
	print("  0                         convert player folders")
	print("  1                         convert entire exports")
	print("")
	
	# Ask the user for a run type, read a single character input
	run_type = input("You can also choose a type now: ")
	
	# Check if run_type is between 0 and 1, ask again otherwise
	while run_type not in ["0", "1"]:
		print("Invalid run type, please try again or close the program.")
		print("")
		run_type = input("Choose a type: ")
	
	return run_type


def convert_players():
	from lib.convertFaceFolder import convertFaceFolder
	
	print("- Converting player folders...")
	print("-")
	
	OUTPUT_FOLDER = "players_converted"
	# Check if the output folder exists and create it if it doesn't
	if not os.path.isdir(OUTPUT_FOLDER):
		os.mkdir(OUTPUT_FOLDER)
	
	# For each player folder in the "players_to_convert" folder
	for player_folder in os.listdir("players_to_convert"):
		if player_folder.lower() == 'common':
			continue
		
		player_folder_path = os.path.join("players_to_convert", player_folder)
		if not os.path.isdir(player_folder_path):
			continue
		
		folders_to_convert = []
		
		# For each folder in the player folder
		for folder in os.listdir(player_folder_path):
			if folder.lower() == 'common':
				continue
			
			folder_path = os.path.join(player_folder_path, folder)
			if os.path.isdir(folder_path):
				# Add it to the list of folders to convert
				folders_to_convert.append(folder_path)
		
		# Create the player destination folder after deleting it if it already exists
		player_destination_folder = os.path.join(OUTPUT_FOLDER, player_folder)
		if os.path.isdir(player_destination_folder):
			shutil.rmtree(player_destination_folder)
		os.mkdir(player_destination_folder)
		
		destination_face_folder = os.path.join(player_destination_folder, "Face")
		os.mkdir(destination_face_folder)
		
		destination_common_folder = os.path.join(player_destination_folder, "Common")
		os.mkdir(destination_common_folder)
		
		# Convert the player folder
		print(f"- {player_folder}")
		convertFaceFolder(folders_to_convert, destination_face_folder, destination_common_folder)
		
		if len(os.listdir(destination_common_folder)) == 0:
			os.rmdir(destination_common_folder)


def convert_teams():
	from lib.convertTeam import convertTeam
	
	# Check if the "EDIT00000000" file exists in the "exports_to_convert" folder
	input_savefile_path = ijoin("exports_to_convert", "EDIT00000000")
	if input_savefile_path is None:
		print("- An \"EDIT00000000\" savefile with the team's data is needed")
		print("- in the \"exports_to_convert\" folder.")
		print("- Please copy it from the PES19 savedata folder.")
		print("-")
		input("Press Enter to exit...")
		exit()
	
	print("- Converting exports...")
	print("-")
	
	OUTPUT_FOLDER = "exports_converted"
	# Check if the output folder exists and create it if it doesn't
	if not os.path.isdir(OUTPUT_FOLDER):
		os.mkdir(OUTPUT_FOLDER)
	
	# For each export folder in the "exports_to_convert" folder
	for export_folder in os.listdir("exports_to_convert"):
		export_folder_path = os.path.join("exports_to_convert", export_folder)
		if not os.path.isdir(export_folder_path):
			continue
		
		# Create the export destination folder after deleting it if it already exists
		export_destination_folder = os.path.join(OUTPUT_FOLDER, export_folder)
		if os.path.isdir(export_destination_folder):
			shutil.rmtree(export_destination_folder)
		os.mkdir(export_destination_folder)
		
		# Convert the export folder
		print(f"- {export_folder}")
		convertTeam(export_folder_path, input_savefile_path, export_destination_folder)


if __name__ == "__main__":
	if sys.platform == "win32":
		os.system("color")
	
	print('-')
	print('-')
	print('- 4cc aet converter')
	print('-')
	print('-')
	
	# Check if all the dependencies are installed
	dependency_check()
	
	# Enable the advanced traceback handler
	from traceback_with_variables import activate_by_import as activate_by_import
	from traceback_with_variables import printing_exc, LoggerAsFile
	
	# Enable the logger
	logger = logger_init(__name__)
	
	# Check if an argument has been passed and its value is between 0 and 1
	run_type = run_type_request(sys.argv)
	
	# Run the main function with the logger
	with printing_exc(file_=LoggerAsFile(logger)):
		# Set the working folder to the parent of the folder of this script
		os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
		
		if run_type == "0":
			convert_players()
		else:
			convert_teams()
	
	# Exit the script
	print("-")
	print("- Done")
	print("-")
	
	if sys.platform == "win32":
		input("Press Enter to exit...")
