import os
import shutil
import struct
import sys
from PIL import Image

from . import save16, save19
from .convertFaceFolder import convertBootsFolder, convertFaceFolder, convertGlovesFolder
from .material import convertTextureFile
from .util import iglob, ijoin

def readString(buffer, offset):
	data = bytearray()
	while offset < len(buffer) and buffer[offset] != 0:
		data.append(buffer[offset])
		offset += 1
	return str(data, 'utf-8')

def writeString(buffer, offset, string):
	data = string.encode('utf-8') + bytes([0])
	for i in range(len(data)):
		buffer[offset + i] = data[i]

#
# Creates pes16 savedata for a player based on pes19 savedata.
#
def convertPlayerSaveData(sourcePlayerData, oldDestinationPlayerData, hasFaceModel, destinationBootsId, destinationGlovesId):
	(oldPlayerData, oldPlayerAestheticsData) = oldDestinationPlayerData
	playerData = oldPlayerData[:]
	aestheticsData = oldPlayerAestheticsData[:]
	
	sourceAestheticsData = sourcePlayerData[116:]
	
	def readBits(byteOffset, bitOffset, bitCount):
		(word32, ) = struct.unpack('< I', sourceAestheticsData[byteOffset : byteOffset + 4])
		return (word32 >> bitOffset) & ((1 << bitCount) - 1)
	
	def writeBits(byteOffset, bitOffset, bitCount, value):
		(word32, ) = struct.unpack('< I', aestheticsData[byteOffset : byteOffset + 4])
		# Mask the bits to be overwritten
		word32 = word32 & ~(((1 << bitCount) - 1) << bitOffset)
		# Add the new bits
		word32 = word32 | (value << bitOffset)
		aestheticsData[byteOffset : byteOffset + 4] = struct.pack('< I', word32)
	
	def cap(maximum, default, value):
		if value > maximum:
			return default
		return value
	
	writeString(playerData, 50, readString(sourcePlayerData, 52)[0:45]) # player name
	writeString(playerData, 96, readString(sourcePlayerData, 98)[0:15]) # shirt name
	
	playerData[23] |= 128
	#playerData[27] |= 128
	
	
	aestheticsData[12 : 19] = sourceAestheticsData[12 : 19] # body physique
	aestheticsData[22 : 72] = sourceAestheticsData[22 : 72] # ingame face
	
	bootsId = readBits(4, 4, 14)
	glovesId = readBits(4, 18, 14)
	
	if destinationBootsId is not None:
		pass
	elif bootsId < 39:
		destinationBootsId = 0
	else:
		destinationBootsId = 55
	writeBits(4, 4, 14, destinationBootsId)
	
	if destinationGlovesId is not None:
		pass
	elif glovesId == 0:
		destinationGlovesId = 0
	elif glovesId < 11:
		destinationGlovesId = glovesId
	else:
		destinationGlovesId = 11
	writeBits(4, 18, 14, destinationGlovesId)
	
	if hasFaceModel:
		writeBits(4, 0, 4, 0x0c) # edited bits
	else:
		writeBits(4, 0, 4, 0x0f) # edited bits
	
	writeBits(8, 0, 32, 0) # base copy id
	writeBits(19, 0, 6, 0) # wrist tape color
	writeBits(19, 6, 2, 0) # wrist tape enabled
	writeBits(20, 0, 6, readBits(20, 0, 6)) # glasses
	writeBits(20, 6, 2, readBits(20, 6, 2)) # sleeves
	writeBits(21, 0, 2, readBits(21, 0, 2)) # inners
	writeBits(21, 2, 2, readBits(21, 2, 2)) # socks
	writeBits(21, 4, 2, readBits(21, 4, 2)) # undershorts
	writeBits(21, 6, 1, readBits(21, 6, 1)) # shirttail
	writeBits(21, 7, 1, 0) # ankle taping
	writeBits(22, 0, 4, 0) # winter gloves
	
	skinColor = readBits(45, 0, 3)
	if skinColor == 7:
		# reset invisible skin
		skinColor = 1
	writeBits(45, 0, 3, skinColor)
	
	writeBits(45, 3, 5, cap(3, 0, readBits(45, 3, 5))) # cheek type
	writeBits(46, 0, 3, cap(5, 0, readBits(46, 0, 3))) # forehead type
	writeBits(46, 3, 5, cap(12, 0, readBits(46, 3, 5))) # facial hair type
	writeBits(47, 0, 3, cap(4, 0, readBits(47, 0, 3))) # laughter lines type
	writeBits(47, 3, 3, cap(6, 0, readBits(47, 3, 3))) # upper eyelid type
	writeBits(48, 0, 3, cap(2, 0, readBits(48, 0, 3))) # lower eyelid type
	writeBits(50, 0, 3, cap(5, 0, readBits(50, 0, 3))) # eyebrow type
	writeBits(50, 5, 2, cap(2, 0, readBits(50, 5, 2))) # neck line type
	writeBits(52, 0, 3, cap(6, 0, readBits(52, 0, 3))) # nose type
	writeBits(53, 0, 3, cap(3, 0, readBits(53, 0, 3))) # upper lip type
	writeBits(53, 3, 3, cap(2, 0, readBits(53, 3, 3))) # lower lip type
	
	return (playerData, aestheticsData)

def mkdir(containingDirectory, name):
	existingDirectory = ijoin(containingDirectory, name)
	if existingDirectory is not None:
		return existingDirectory
	newDirectory = os.path.join(containingDirectory, name)
	os.mkdir(newDirectory)
	return newDirectory

#
# Converts a player in a pes19 export directory into a pes16 directory, and creates the save data for that player.
# If possible, this will create a single face folder containing the entire model.
# If the pes19 player doesn't have a face folder (and therefore has an ingame face), this will instead
# create boots and gloves folders.
#
def convertPlayer(sourceDirectory, destinationDirectory, relativePlayerId, bootsGlovesBaseId, sourcePlayerData, oldDestinationPlayerData):
	(bootsGlovesIdData, ) = struct.unpack('< I', sourcePlayerData[120 : 124])
	sourceBootsId = (bootsGlovesIdData >> 4) & ((1 << 14) - 1)
	sourceGlovesId = (bootsGlovesIdData >> 18) & ((1 << 14) - 1)
	
	#
	# Find source folders
	#
	sourceFaceDirectory = None
	sourceFacesDirectory = ijoin(sourceDirectory, "Faces")
	if sourceFacesDirectory is not None:
		sourceFaceDirectories = iglob(sourceFacesDirectory, "???%02i*" % relativePlayerId)
		if len(sourceFaceDirectories) > 0:
			if len(sourceFaceDirectories) > 1:
				print("WARNING: Found more than 1 face folder for player %02i, using '%s'" % (relativePlayerId, sourceFaceDirectories[0]))
			sourceFaceDirectory = sourceFaceDirectories[0]
	else:
		print("WARNING: Cannot find Faces folder in export '%s'" % sourceDirectory)
	
	sourceBootDirectory = None
	if sourceBootsId is not None:
		sourceBootsDirectory = ijoin(sourceDirectory, "Boots")
		if sourceBootsDirectory is not None:
			sourceBootDirectories = iglob(sourceBootsDirectory, "k%04i*" % sourceBootsId)
			if len(sourceBootDirectories) > 0:
				if len(sourceBootDirectories) > 1:
					print("WARNING: Found more than 1 boots folder for boots k%04i, using '%s'" % (sourceBootsId, sourceBootDirectories[0]))
				sourceBootDirectory = sourceBootDirectories[0]
	
	sourceGloveDirectory = None
	if sourceGlovesId is not None:
		sourceGlovesDirectory = ijoin(sourceDirectory, "Gloves")
		if sourceGlovesDirectory is not None:
			sourceGloveDirectories = iglob(sourceGlovesDirectory, "g%04i*" % sourceGlovesId)
			if len(sourceGloveDirectories) > 0:
				if len(sourceGloveDirectories) > 1:
					print("WARNING: Found more than 1 gloves folder for boots g%04i, using '%s'" % (sourceGlovesId, sourceGloveDirectories[0]))
				sourceGloveDirectory = sourceGloveDirectories[0]
	
	
	#
	# Build face/boots/gloves folders
	#
	
	commonDirectory = mkdir(destinationDirectory, "Common")
	bootsId = None
	glovesId = None
	
	facePortraitFound = False
	if sourceFaceDirectory is not None:
		#
		# Build a unified face folder containing the face, boots, and gloves
		#
		
		sourceModelDirectories = [sourceFaceDirectory]
		if sourceBootDirectory is not None:
			sourceModelDirectories.append(sourceBootDirectory)
		if sourceGloveDirectory is not None:
			sourceModelDirectories.append(sourceGloveDirectory)
		
		faceDirectory = mkdir(mkdir(destinationDirectory, "Faces"), os.path.basename(sourceFaceDirectory))
		convertFaceFolder(sourceModelDirectories, faceDirectory, commonDirectory)
		
		portraitFilename = ijoin(sourceFaceDirectory, "portrait.dds")
		if portraitFilename is not None:
			facePortraitFound = True
			shutil.copy(portraitFilename, os.path.join(faceDirectory, "portrait.dds"))
		
		hasFaceModel = True
	else:
		#
		# This player has an ingame face, which we want to retain.
		# Convert the boots and gloves separately.
		#
		
		if sourceBootDirectory is not None:
			bootsId = bootsGlovesBaseId + relativePlayerId
			bootsDirectoryName = "k%04i" % bootsId
			bootsDirectoryTitle = os.path.basename(sourceBootDirectory)[5:].strip(" -_")
			if len(bootsDirectoryTitle) > 0:
				bootsDirectoryName += " - %s" % bootsDirectoryTitle
			destinationBootsDirectory = mkdir(mkdir(destinationDirectory, "Boots"), bootsDirectoryName)
			convertBootsFolder(sourceBootDirectory, destinationBootsDirectory, commonDirectory)
		
		if sourceGloveDirectory is not None:
			glovesId = bootsGlovesBaseId + relativePlayerId
			gloveDirectoryName = "g%04i" % glovesId
			gloveDirectoryTitle = os.path.basename(sourceGloveDirectory)[5:].strip(" -_")
			if len(gloveDirectoryTitle) > 0:
				gloveDirectoryName += " - %s" % gloveDirectoryTitle
			destinationGlovesDirectory = mkdir(mkdir(destinationDirectory, "Gloves"), gloveDirectoryName)
			convertGlovesFolder(sourceGloveDirectory, destinationGlovesDirectory, commonDirectory)
		
		hasFaceModel = False
	
	#
	# Convert portrait
	#
	if not facePortraitFound:
		sourcePortraitsDirectory = ijoin(sourceDirectory, "Portraits")
		if sourcePortraitsDirectory is not None:
			portraitFilenames = iglob(sourcePortraitsDirectory, "player_???%02i.dds")
			if len(portraitFilenames) > 0:
				if len(portraitFilenames) > 1:
					print("WARNING: Found more then 1 portrait for player %02i, using '%s'" % (relativePlayerId, portraitFilenames[0]))
				portraitsDirectory = mkdir(destinationDirectory, "Portraits")
				shutil.copy(portraitFilenames[0], os.path.join(portraitsDirectory, "player_XXX%02i.dds" % relativePlayerId))
	
	#
	# Convert save data, lookup boots and gloves ID
	#
	newDestinationPlayerData = convertPlayerSaveData(sourcePlayerData, oldDestinationPlayerData, hasFaceModel, bootsId, glovesId)
	
	return newDestinationPlayerData


def getTeamName(sourceDirectory):
	directoryName = os.path.basename(sourceDirectory.rstrip('/\\'))
	parts = directoryName.replace("_", " ").strip().split(" ")
	return parts[0]

def getTeamId(teamListFile, teamName):
	for line in open(teamListFile, 'r').read().splitlines():
		pos = line.find(" ")
		if pos == -1:
			continue
		idString = line[0:pos].strip()
		try:
			id = int(idString)
		except:
			continue
		nameString = line[pos + 1:].strip().strip("/")
		if nameString.lower() == teamName.lower():
			return id
	return None

def convertKitConfigFile(kitConfigFile, destinationDirectory):
	destinationFilename = os.path.join(destinationDirectory, os.path.basename(kitConfigFile))
	
	kitConfigData = bytearray(open(kitConfigFile, 'rb').read())
	kitConfigData[1] = 176 # shirt type
	kitConfigData[3] = 16 # pants type
	kitConfigData[20] = 105 # collar
	kitConfigData[21] = 105 # winter collar
	#kitConfigData[27] |= 128 # tight shirts
	maskTexture = readString(kitConfigData, 72)
	if "_srm" in maskTexture:
		maskTexture = maskTexture.replace("_srm", "_mask")
		writeString(kitConfigData, 72, maskTexture)
	open(destinationFilename, 'wb').write(kitConfigData)

def convertKitTextureFile(kitTextureFile, destinationDirectory):
	basename = os.path.basename(kitTextureFile)
	if "_srm" in basename:
		#
		# Kits don't have specular maps in pes16; they have mask maps.
		# Create a sensible default one.
		#
		pos = basename.rfind('.')
		if pos == -1:
			name = basename
		else:
			name = basename[:pos]
		name = name.replace("_srm", "_mask")
		maskImage = Image.new('RGBA', (4, 4), (150, 130, 0, 255))
		maskImageFilename = os.path.join(destinationDirectory, "%s.png" % name)
		maskImage.save(maskImageFilename)
		convertTextureFile(maskImageFilename, destinationDirectory)
		os.remove(maskImageFilename)
	else:
		convertTextureFile(kitTextureFile, destinationDirectory)

def convertTeamFiles(sourceDirectory, destinationDirectory):
	#
	# note.txt
	#
	noteTxtFilenames = iglob(sourceDirectory, "*note*.txt")
	if len(noteTxtFilenames) == 0:
		print("WARNING: No note.txt found in team export folder '%s'" % sourceDirectory)
	for filename in noteTxtFilenames:
		shutil.copy(filename, os.path.join(destinationDirectory, os.path.basename(filename)))
	
	#
	# Logo
	#
	logoDirectory = ijoin(sourceDirectory, "Logo")
	if logoDirectory is None:
		print("WARNING: No logo folder found in team export folder '%s'" % sourceDirectory)
	else:
		shutil.copytree(logoDirectory, os.path.join(destinationDirectory, "Logo"))
	
	#
	# Other
	#
	otherDirectory = ijoin(sourceDirectory, "Other")
	if otherDirectory is not None:
		shutil.copytree(otherDirectory, os.path.join(destinationDirectory, "Other"))
	
	#
	# Kit Configs
	#
	kitConfigDirectory = ijoin(sourceDirectory, "Kit Configs")
	if kitConfigDirectory is None:
		print("WARNING: No kit config folder found in team export folder '%s'" % sourceDirectory)
	else:
		destinationKitConfigDirectory = os.path.join(destinationDirectory, "Kit Configs")
		os.mkdir(destinationKitConfigDirectory)
		
		for kitConfigFile in os.listdir(kitConfigDirectory):
			kitConfigPath = os.path.join(kitConfigDirectory, kitConfigFile)
			if os.path.isdir(kitConfigPath):
				#
				# kit config directory can contain its contents in a subdirectory. So recurse, once.
				#
				for kitConfigFile2 in os.listdir(kitConfigPath):
					kitConfigPath2 = os.path.join(kitConfigPath, kitConfigFile2)
					convertKitConfigFile(kitConfigPath2, destinationKitConfigDirectory)
			else:
				convertKitConfigFile(kitConfigPath, destinationKitConfigDirectory)
	
	#
	# Kit Textures
	#
	kitTextureDirectory = ijoin(sourceDirectory, "Kit Textures")
	if kitTextureDirectory is None:
		print("WARNING: No kit texture folder found in team export folder '%s'" % sourceDirectory)
	else:
		destinationKitTextureDirectory = os.path.join(destinationDirectory, "Kit Textures")
		os.mkdir(destinationKitTextureDirectory)
		
		for kitTextureFile in os.listdir(kitTextureDirectory):
			kitTexturePath = os.path.join(kitTextureDirectory, kitTextureFile)
			if os.path.isdir(kitTexturePath):
				#
				# kit texture directory can contain its contents in a subdirectory. So recurse, once.
				#
				for kitTextureFile2 in os.listdir(kitTexturePath):
					kitTexturePath2 = os.path.join(kitTexturePath, kitTextureFile2)
					convertKitTextureFile(kitTexturePath2, destinationKitTextureDirectory)
			else:
				convertKitTextureFile(kitTexturePath, destinationKitTextureDirectory)

def convertTeam(sourceDirectory, sourceSaveFile, destinationDirectory):
	teamName = getTeamName(sourceDirectory)
	
	sourceTeamId = getTeamId(os.path.join(os.path.dirname(os.path.realpath(__file__)), "teams_list_19.txt"), teamName)
	destinationTeamId = getTeamId(os.path.join(os.path.dirname(os.path.realpath(__file__)), "teams_list_16.txt"), teamName)
	# TODO: support a list for this
	bootsGlovesBaseId = 101 + (destinationTeamId - 701) * 25
	
	print("Converting team %i - /%s/" % (sourceTeamId, teamName))
	
	print("  Loading save data")
	sourceSave = save19.SaveFile()
	sourceSave.load(sourceSaveFile)
	
	destinationSave = save16.SaveFile()
	destinationSave.load(os.path.join(os.path.dirname(os.path.realpath(__file__)), "EDIT00000000_16"))
	
	sourcePlayers = save19.loadPlayers(sourceSave.payload)
	oldDestinationPlayers = save16.loadPlayers(destinationSave.payload)
	newDestinationPlayers = {}
	
	for i in range(23):
		print("  Converting player %02i" % (i + 1))
		sourcePlayerId = sourceTeamId * 100 + i + 1
		destinationPlayerId = destinationTeamId * 100 + i + 1
		
		if sourcePlayerId not in sourcePlayers:
			print("ERROR: Player %s not found in pes19 save" % sourcePlayerId)
		if destinationPlayerId not in oldDestinationPlayers:
			print("ERROR: Player %s not found in pes16 save" % destinationPlayerId)
		
		sourcePlayer = sourcePlayers[sourcePlayerId]
		oldDestinationPlayer = oldDestinationPlayers[destinationPlayerId]
		
		(oldDestinationPlayerData, oldDestinationPlayerAestheticsData) = oldDestinationPlayer
		if oldDestinationPlayerData is None or oldDestinationPlayerAestheticsData is None:
			print("ERROR: Incomplete player %s found in pes16 save" % destinationPlayerId)
		
		newDestinationPlayers[destinationPlayerId] = convertPlayer(
			sourceDirectory,
			destinationDirectory,
			i + 1,
			bootsGlovesBaseId,
			sourcePlayer,
			oldDestinationPlayer,
		)
	
	print("  Converting kits")
	commonDirectory = ijoin(destinationDirectory, "Common")
	if commonDirectory is not None and len(os.listdir(commonDirectory)) == 0:
		os.rmdir(commonDirectory)
	
	convertTeamFiles(sourceDirectory, destinationDirectory)
	
	print("  Creating save")
	save16.savePlayers(destinationSave.payload, newDestinationPlayers)
	destinationSave.save(os.path.join(destinationDirectory, "EDIT00000000"))

if __name__ == "__main__":
	if len(sys.argv) != 4:
		print("Usage: convertTeam <pes19 export folder> <pes19 savefile> <destination folder>")
		sys.exit(1)
	
	convertTeam(sys.argv[1], sys.argv[2], sys.argv[3])
