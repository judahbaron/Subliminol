import sys
import zipfile

SUBLIMINOL_SOURCE_FILES = ["Subliminol.py", "Subliminol (Windows).sublime-keymap", "Subliminol.sublime-settings"]
SUBLIMINOL_DATA_FILES = ["Batch File.tmLanguage", "Neon.tmTheme"]


def write_package(package_filepath, file_map):
	print("Writing to package:")
	lmax = 0
	for key, value in file_map.items():
		if len(value) > lmax: lmax = len(value)
	fmt_str = "     ADD: {0:<" + str(lmax+5) + "}({1})"
	with zipfile.ZipFile(package_filepath, "w") as out_zip:
		
		for file, archive_path in file_map.iteritems():
			print(fmt_str.format(archive_path, file))
			out_zip.write(file, archive_path)

def gather_files(project_dir):
	print("Gathering files:")
	file_map = {}
	for src in SUBLIMINOL_SOURCE_FILES:
		file_map["{0}/{1}".format(project_dir, src)] = src
	for dat in SUBLIMINOL_DATA_FILES:
		file_map["{0}/data/{1}".format(project_dir, dat)] = dat
	return file_map

def do_build():
	print "STARTING SUBLIMINOL BUILD"
	file_map = gather_files(sys.argv[1].replace("\\", "/"))
	output_file = sys.argv[2].replace("\\", "/")
	print("   file_map:".format(file_map))
	for k, v in file_map.items():
		print("     {0}:     {1}".format(k, v))
	print("   output_file:\n          {}".format(output_file))

	# print("SUBLIMINOL BUILD - WRITING: {0}".format(output_file))
	write_package(output_file, file_map)
	print("SUBLIMINOL BUILD COMPLETE:\n\twrote {0}".format(output_file))

do_build()