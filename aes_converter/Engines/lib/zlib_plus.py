import os
import zlib
import struct

class DecodeError(Exception):
	pass

def encodeHeader(compressedBuffer, uncompressedBuffer):
	return struct.pack('< 3B 5s II',
		0x00,
		0x10,
		0x01,
		'WESYS'.encode('UTF-8'),
		len(compressedBuffer),
		len(uncompressedBuffer),
	)

def decodeHeader(byteBuffer):
	if len(byteBuffer) < 16:
		return None
	header = byteBuffer[0:16]
	(magic, ) = struct.unpack('< 4x 4s 8x', header)
	if magic != b'ESYS':
		return None
	return memoryview(byteBuffer)[16:]

def compress(byteBuffer):
	compressedBuffer = zlib.compress(byteBuffer)
	return encodeHeader(compressedBuffer, byteBuffer) + compressedBuffer

def tryCompress(byteBuffer):
	compressedBuffer = zlib.compress(byteBuffer)
	if len(compressedBuffer) + 16 < len(byteBuffer):
		return encodeHeader(compressedBuffer, byteBuffer) + compressedBuffer
	else:
		return byteBuffer

def decompress(byteBuffer):
	compressedBuffer = decodeHeader(byteBuffer)
	if compressedBuffer is None:
		raise DecodeError()
	try:
		return zlib.decompress(compressedBuffer)
	except Exception:
		raise DecodeError()

def tryDecompress(byteBuffer):
	compressedBuffer = decodeHeader(byteBuffer)
	if compressedBuffer is None:
		return byteBuffer
	try:
		return zlib.decompress(compressedBuffer)
	except Exception:
		raise DecodeError()

def isCompressed(byteBuffer):
	compressedBuffer = decodeHeader(byteBuffer)
	return compressedBuffer is not None

# Returns the hex representation of the bytes read from the specified file
def get_bytes_hex(file_path, start, length):
    with open(file_path, 'rb') as file:
        file.seek(start)  # Skip to the start position
        bytes_data = file.read(length)
    return ''.join(f'{byte:02x}' for byte in bytes_data).upper()

# Returns the ascii representation of the bytes read from the specified file
def get_bytes_ascii(file_path, start, length):
	with open(file_path, 'rb') as file:
		file.seek(start)  # Skip to the start position
		bytes_data = file.read(length)
	return ''.join(chr(byte) for byte in bytes_data)


def unzlib_file(source_file_path, destination_file_path = None):
    """
    A function to unzlib a file if needed and copy it to a destination file path.

    :param source_file_path: str - the file path of the source file to unzlib
    :param destination_file_path: str (optional) - the file path to save the unzlibbed file, defaults to None

    :return: bool - True if the file needed to be unzlibbed, False otherwise
    """

    unzlib_needed = False
    if destination_file_path is None:
        destination_file_path = source_file_path

    # Check if it is zlibbed (WESYS label starting from index 3)
    if get_bytes_ascii(source_file_path, 3, 5) == 'WESYS':

        # Unzlib it
        with open(source_file_path, 'rb') as f:
            data = decompress(f.read())

        with open(destination_file_path, 'wb') as f:
            f.write(data)

        unzlib_needed = True

    return unzlib_needed


def zlib_file(source_file_path, destination_file_path = None):
    """
    A function to zlib a file if needed and copy it to a destination file path.

    :param source_file_path: str - the file path of the source file to zlib
    :param destination_file_path: str (optional) - the file path to save the zlibbed file, defaults to None

    :return: bool - True if the file needed to be zlibbed, False otherwise
    """

    zlib_needed = False
    if destination_file_path is None:
        destination_file_path = source_file_path

    # Check if it is zlibbed (WESYS label starting from index 3)
    if get_bytes_ascii(source_file_path, 3, 5) == 'WESYS':
        pass # File is already zlibbed, don't do anything
    else:
        # Zlib it
        with open(source_file_path, 'rb') as f:
            data = compress(f.read())

        with open(destination_file_path, 'wb') as f:
            f.write(data)

        zlib_needed = True

    return zlib_needed


def zlib_files_in_folder(path, extension):
    """
    A function that walks through a folder specified by 'path' and compresses files with the given 'extension' using zlib compression.

    :param path: The path of the folder to search for files.
    :param extension: The file extension to filter files for compression.
    """

    to_zlib = []

    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(extension):
                to_zlib.append(os.path.join(root, file))
         
    i = 1
    total = len(to_zlib)
    pad = len(str(total))
    for file_path in to_zlib:
        sys.stdout.write("Zlibbing files (" + str(i) + '/' + str(total) + ')...' + pad*' ' + '\r') #Log process
        sys.stdout.flush()
        zlib_file(file_path)
        i = i + 1