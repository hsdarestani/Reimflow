from pathlib import Path
import os, plistlib
team=os.environ['IOS_TEAM_ID']
profile=os.environ['IOS_PROVISIONING_PROFILE_SPECIFIER']
bundle=os.environ.get('IOS_BUNDLE_ID','sbs.smarbiz.reimflow')
data={
 'method':'app-store-connect','destination':'export','signingStyle':'manual',
 'teamID':team,'provisioningProfiles':{bundle:profile},
 'manageAppVersionAndBuildNumber':False,'stripSwiftSymbols':True,
 'uploadSymbols':True,
}
file=Path("artifacts/ExportOptions.plist")
file.parent.mkdir(parents=True,exist_ok=True)
with file.open("wb") as f:plistlib.dump(data,f)
print("Prepared signed App Store Connect export options")
