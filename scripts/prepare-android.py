from pathlib import Path
import os, re
from xml.etree import ElementTree as ET
project = Path("android")
gradle = project / "app" / "build.gradle"
data = gradle.read_text()
assert "buildTypes {" in data and "android {" in data, "Unsupported Capacitor Gradle template"
# Publisher places android/key.properties and a separate upload keystore.
assert (project / "key.properties").is_file(), "Publisher Android signing not provisioned"
assert (project / "upload-keystore.jks").is_file(), "Publisher keystore not provisioned"
prefix = """def rfProps = new java.util.Properties()
def rfPropFile = rootProject.file("key.properties")
rfPropFile.withInputStream { rfProps.load(it) }
"""
if "def rfProps" not in data:
    data = prefix + data
if "rfProps['storePassword']" not in data:
    data = data.replace("android {", """android {
    signingConfigs {
        release {
            storeFile file("../upload-keystore.jks")
            storePassword rfProps['storePassword']
            keyAlias rfProps['keyAlias']
            keyPassword rfProps['keyPassword']
        }
    }
""",1)
if "signingConfig signingConfigs.release" not in data:
    data = re.sub(r"(buildTypes\s*\{\s*release\s*\{)", r"\1\n            signingConfig signingConfigs.release",data,count=1)
assert "signingConfig signingConfigs.release" in data
version = os.getenv("APP_VERSION_NAME", "1.0.0")
number = int(os.getenv("APP_BUILD_NUMBER", "1"))
data = re.sub(r'versionCode\s+\d+',f'versionCode {number}',data,count=1)
data = re.sub(r'versionName\s+["\'][^"\']+["\']',f'versionName "{version}"',data,count=1)
gradle.write_text(data)
manifest = project / "app/src/main/AndroidManifest.xml"
ns = "{http://schemas.android.com/apk/res/android}"
ET.register_namespace('android','http://schemas.android.com/apk/res/android')
root = ET.parse(manifest).getroot()
if not any(x.get(ns+'name') == 'android.permission.RECORD_AUDIO' for x in root.findall('uses-permission')):
    root.insert(0,ET.Element('uses-permission',{ns+'name':'android.permission.RECORD_AUDIO'}))
ET.ElementTree(root).write(manifest,encoding="utf-8",xml_declaration=True)
print("Android signing, version and microphone permission configured")
