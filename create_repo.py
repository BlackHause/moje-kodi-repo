import os
import hashlib
import zipfile
import shutil
from xml.etree import ElementTree as ET

# --- NASTAVENÍ ---
ADDON_ID = "plugin.video.mycinema"
REPO_ID = "repository.mycinema"
REPO_NAME = "MyCinema Repozitář"
GITHUB_USERNAME = "BlackHause"
# --- KONEC NASTAVENÍ ---

def create_zip(addon_id, version):
    print(f"Vytvářím ZIP pro {addon_id} verze {version}...")
    source_dir = addon_id
    zip_filename = f"{addon_id}-{version}.zip"

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                archive_path = os.path.relpath(file_path, os.path.join(source_dir, '..'))
                zf.write(file_path, archive_path)
    print("  -> ZIP vytvořen.")

def create_repo_addon(version):
    print("Vytvářím doplněk pro repozitář...")
    repo_dir = REPO_ID
    os.makedirs(repo_dir, exist_ok=True)

    repo_url = f"https://{GITHUB_USERNAME}.github.io/{os.path.basename(os.getcwd())}"

    addon_xml_content = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="{REPO_ID}" name="{REPO_NAME}" version="{version}" provider-name="{GITHUB_USERNAME}">
    <extension point="xbmc.addon.repository" name="{REPO_NAME}">
        <info compressed="false">{repo_url}/addons.xml</info>
        <checksum>{repo_url}/addons.xml.md5</checksum>
        <datadir zip="true">{repo_url}/zips/</datadir>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary>Repozitář pro MyCinema</summary>
        <description></description>
        <platform>all</platform>
        <assets>
            <icon>icon.png</icon>
        </assets>
    </extension>
</addon>'''
    with open(os.path.join(repo_dir, "addon.xml"), "w", encoding="utf-8") as f:
        f.write(addon_xml_content)

    shutil.copy(os.path.join(ADDON_ID, 'icon.png'), os.path.join(repo_dir, 'icon.png'))
    create_zip(REPO_ID, version)
    shutil.rmtree(repo_dir) # Smažeme dočasnou složku

def generate_addons_xml():
    print("Generuji addons.xml...")
    addons = []
    for file in os.listdir('.'):
        if file.startswith('plugin.') or file.startswith('repository.'):
            if os.path.isdir(file):
                addons.append(file)

    root = ET.Element('addons')
    for addon_id in addons:
        try:
            tree = ET.parse(os.path.join(addon_id, 'addon.xml'))
            root.append(tree.getroot())
        except Exception as e:
            print(f"  -> Chyba při čtení {addon_id}/addon.xml: {e}")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write('addons.xml', encoding='utf-8', xml_declaration=True)
    print("  -> addons.xml vytvořen.")

    with open('addons.xml', 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    with open('addons.xml.md5', 'w') as f:
        f.write(md5)
    print("  -> addons.xml.md5 vytvořen.")


if __name__ == '__main__':
    # Získání verze z hlavního doplňku
    try:
        tree = ET.parse(os.path.join(ADDON_ID, 'addon.xml'))
        version = tree.getroot().get('version')
    except Exception:
        version = "1.0.0"
        print(f"Varování: Nepodařilo se načíst verzi, používám {version}")

    # Vytvoření zips složky
    os.makedirs('zips', exist_ok=True)

    # Zabalení hlavního doplňku
    create_zip(ADDON_ID, version)

    # Vytvoření a zabalení repozitáře
    create_repo_addon("1.0.0")

    # Přesunutí zipů do složky zips
    for file in os.listdir('.'):
        if file.endswith('.zip'):
            shutil.move(file, os.path.join('zips', file))

    # Generování finálního XML
    generate_addons_xml()

    print("\nREPOSITÁŘ ÚSPĚŠNĚ VYTVOŘEN!")