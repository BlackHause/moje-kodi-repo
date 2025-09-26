# -*- coding: utf-8 -*-
# Module: default
# Author: BlackHause
# Created on: 15.9.2025
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import io
import os
import sys
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
import requests.cookies
from xml.etree import ElementTree as ET
import hashlib
from md5crypt import md5crypt
import traceback
import json
import unidecode
import re
import zipfile
import uuid
import series_manager
import themoviedb
from collections import defaultdict

try:
    from urllib import urlencode
    from urlparse import parse_qsl, urlparse
except ImportError:
    from urllib.parse import urlencode
    from urllib.parse import parse_qsl, urlparse

try:
    from xbmc import translatePath
except ImportError:
    from xbmcvfs import translatePath

BASE = 'https://webshare.cz'
API = BASE + '/api/'
UA = "Mozilla/50 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"
HEADERS = {'User-Agent': UA, 'Referer':BASE}
REALM = ':Webshare:'
CATEGORIES = ['','video','images','audio','archives','docs','adult']
SORTS = ['','recent','rating','largest','smallest']
SEARCH_HISTORY = 'search_history'
NONE_WHAT = '%#NONE#%'
BACKUP_DB = 'D1iIcURxlR'

_url = sys.argv[0]
_handle = int(sys.argv[1])
_addon = xbmcaddon.Addon()
_session = requests.Session()
_session.headers.update(HEADERS)
_profile = translatePath( _addon.getAddonInfo('profile'))
# ... ostatní proměnné
_profile = translatePath( _addon.getAddonInfo('profile'))
try:
    _profile = _profile.decode("utf-8")
except:
    pass

BACKEND_URL = "https://mycinema.up.railway.app/api"
try:
    _profile = _profile.decode("utf-8")
except:
    pass

# --- DEFINICE CEST K IKONÁM (SPOLEHLIVÉ SYSTÉMOVÉ IKONY) ---
ICON_FAVOURITES = 'DefaultFavourites.png' # Pro žebříčky
ICON_CHANNELS = 'DefaultPVRChannels.png' # Pro TV tipy


def get_url(**kwargs):
    return '{0}?{1}'.format(_url, urlencode(kwargs, 'utf-8'))

def api(fnct, data):
    response = _session.post(API + fnct + "/", data=data)
    return response

def is_ok(xml):
    status = xml.find('status').text
    return status == 'OK'

def popinfo(message, heading=_addon.getAddonInfo('name'), icon=xbmcgui.NOTIFICATION_INFO, time=3000, sound=False): #NOTIFICATION_WARNING NOTIFICATION_ERROR
    xbmcgui.Dialog().notification(heading, message, icon, time, sound=sound)

def login():
    username = _addon.getSetting('wsuser')
    password = _addon.getSetting('wspass')
    if username == '' or password == '':
        popinfo(_addon.getLocalizedString(30101), sound=True)
        _addon.openSettings()
        return
    response = api('salt', {'username_or_email': username})
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        salt = xml.find('salt').text
        try:
            encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8'))).hexdigest()
            pass_digest = hashlib.md5(username.encode('utf-8') + REALM + encrypted_pass.encode('utf-8')).hexdigest()
        except TypeError:
            encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8')).encode('utf-8')).hexdigest()
            pass_digest = hashlib.md5(username.encode('utf-8') + REALM.encode('utf-8') + encrypted_pass.encode('utf-8')).hexdigest()
        response = api('login', {'username_or_email': username, 'password': encrypted_pass, 'digest': pass_digest, 'keep_logged_in': 1})
        xml = ET.fromstring(response.content)
        if is_ok(xml):
            token = xml.find('token').text
            _addon.setSetting('token', token)
            return token
        else:
            popinfo(_addon.getLocalizedString(30102), icon=xbmcgui.NOTIFICATION_ERROR, sound=True)
            _addon.openSettings()
    else:
        popinfo(_addon.getLocalizedString(30102), icon=xbmcgui.NOTIFICATION_ERROR, sound=True)
        _addon.openSettings()

def revalidate():
    token = _addon.getSetting('token')
    if len(token) == 0:
        if login():
            return revalidate()
    else:
        response = api('user_data', { 'wst': token })
        xml = ET.fromstring(response.content)
        status = xml.find('status').text
        if is_ok(xml):
            vip = xml.find('vip').text
            if vip != '1':
                popinfo(_addon.getLocalizedString(30103), icon=xbmcgui.NOTIFICATION_WARNING)
            return token
        else:
            if login():
                return revalidate()

def todict(xml, skip=[]):
    result = {}
    for e in xml:
        if e.tag in skip:
            continue
        
        value = e.text if len(list(e)) == 0 else todict(e,skip)
        if e.tag in result:
            if isinstance(result[e.tag], list):
                result[e.tag].append(value)
            else:
                result[e.tag] = [result[e.tag],value]
        else:
            result[e.tag] = value
    return result
            
def sizelize(txtsize, units=['B','KB','MB','GB']):
    if txtsize:
        size = float(txtsize)
        if size < 1024:
            size = str(size) + units[0]
        else:
            size = size / 1024
            if size < 1024:
                size = str(int(round(size))) + units[1]
            else:
                size = size / 1024
                if size < 1024:
                    size = str(round(size,2)) + units[2]
                else:
                    size = size / 1024
                    size = str(round(size,2)) + units[3]
        return size
    return str(txtsize)
    
def labelize(file):
    if 'size' in file:
        size = sizelize(file['size'])
    elif 'sizelized' in file:
        size = file['sizelized']
    else:
        size = '?'
    label = file['name'] + ' (' + size + ')'
    return label
    
def tolistitem(file, addcommands=[]):
    label = labelize(file)
    listitem = xbmcgui.ListItem(label=label)
    if 'img' in file:
        listitem.setArt({'thumb': file['img']})
    listitem.setInfo('video', {'title': label})
    listitem.setProperty('IsPlayable', 'true')
    commands = []
    commands.append(( _addon.getLocalizedString(30211), 'RunPlugin(' + get_url(action='info',ident=file['ident']) + ')'))
    commands.append(( _addon.getLocalizedString(30212), 'RunPlugin(' + get_url(action='download',ident=file['ident']) + ')'))
    if addcommands:
        commands = commands + addcommands
    listitem.addContextMenuItems(commands)
    return listitem

def ask(what):
    if what is None:
        what = ''
    kb = xbmc.Keyboard(what, _addon.getLocalizedString(30007))
    kb.doModal()
    if kb.isConfirmed():
        return kb.getText()
    return None
    
def loadsearch():
    history = []
    try:
        if not os.path.exists(_profile):
            os.makedirs(_profile)
    except Exception as e:
        traceback.print_exc()
    
    try:
        with io.open(os.path.join(_profile, SEARCH_HISTORY), 'r', encoding='utf8') as file:
            fdata = file.read()
            file.close()
            try:
                history = json.loads(fdata, "utf-8")
            except TypeError:
                history = json.loads(fdata)
    except Exception as e:
        traceback.print_exc()

    return history
    
def storesearch(what):
    if what:
        size = int(_addon.getSetting('shistory'))

        history = loadsearch()

        if what in history:
            history.remove(what)

        history = [what] + history
        
        if len(history)>size:
            history = history[:size]

        try:
            with io.open(os.path.join(_profile, SEARCH_HISTORY), 'w', encoding='utf8') as file:
                try:
                    data = json.dumps(history).decode('utf8')
                except AttributeError:
                    data = json.dumps(history)
                file.write(data)
                file.close()
        except Exception as e:
            traceback.print_exc()

def removesearch(what):
    if what:
        history = loadsearch()
        if what in history:
            history.remove(what)
            try:
                with io.open(os.path.join(_profile, SEARCH_HISTORY), 'w', encoding='utf8') as file:
                    try:
                        data = json.dumps(history).decode('utf8')
                    except AttributeError:
                        data = json.dumps(history)
                    file.write(data)
                    file.close()
            except Exception as e:
                traceback.print_exc()

def dosearch(token, what, category, sort, limit, offset, action):
    response = api('search',{'what':'' if what == NONE_WHAT else what, 'category':category, 'sort':sort, 'limit': limit, 'offset': offset, 'wst':token, 'maybe_removed':'true'})
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        
        if offset > 0: #prev page
            listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30206))
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            xbmcplugin.addDirectoryItem(_handle, get_url(action=action, what=what, category=category, sort=sort, limit=limit, offset=offset - limit if offset > limit else 0), listitem, True)
            
        for file in xml.iter('file'):
            item = todict(file)
            commands = []
            commands.append(( _addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='search',toqueue=item['ident'], what=what, offset=offset) + ')'))
            listitem = tolistitem(item,commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=item['ident'],name=item['name']), listitem, False)
        
        try:
            total = int(xml.find('total').text)
        except:
            total = 0
            
        if offset + limit < total: #next page
            listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30207))
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            xbmcplugin.addDirectoryItem(_handle, get_url(action=action, what=what, category=category, sort=sort, limit=limit, offset=offset+limit), listitem, True)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)

def search(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \ " + _addon.getLocalizedString(30201))
    token = revalidate()
    
    updateListing=False
    
    if 'remove' in params:
        removesearch(params['remove'])
        updateListing=True
        
    if 'toqueue' in params:
        toqueue(params['toqueue'],token)
        updateListing=True
    
    what = None
    
    if 'what' in params:
        what = params['what']
    
    if 'ask' in params:
        slast = _addon.getSetting('slast')
        if slast != what:
            what = ask(what)
            if slast != what:
                what = ask(what)
                if what is not None:
                    storesearch(what)
                else:
                    updateListing=True
        else:
            updateListing=True

    if what is not None:
        if 'offset' not in params:
            _addon.setSetting('slast',what)
        else:
            _addon.setSetting('slast',NONE_WHAT)
            updateListing=True
        
        category = params['category'] if 'category' in params else CATEGORIES[int(_addon.getSetting('scategory'))]
        sort = params['sort'] if 'sort' in params else SORTS[int(_addon.getSetting('ssort'))]
        limit = int(params['limit']) if 'limit' in params else int(_addon.getSetting('slimit'))
        offset = int(params['offset']) if 'offset' in params else 0
        dosearch(token, what, category, sort, limit, offset, 'search')
    else:
        _addon.setSetting('slast',NONE_WHAT)
        history = loadsearch()
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30205))
        listitem.setArt({'icon': 'DefaultAddSource.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search',ask=1), listitem, True)
        
        #newest
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30208))
        listitem.setArt({'icon': 'DefaultAddonsRecentlyUpdated.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=NONE_WHAT,sort=SORTS[1]), listitem, True)
        
        #biggest
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30209))
        listitem.setArt({'icon': 'DefaultHardDisk.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=NONE_WHAT,sort=SORTS[3]), listitem, True)
        
        for search in history:
            listitem = xbmcgui.ListItem(label=search)
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            commands = []
            commands.append(( _addon.getLocalizedString(30213), 'Container.Update(' + get_url(action='search',remove=search) + ')'))
            listitem.addContextMenuItems(commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='search',what=search,ask=1), listitem, True)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)

def queue(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \ " + _addon.getLocalizedString(30202))
    token = revalidate()
    updateListing=False
    
    if 'dequeue' in params:
        response = api('dequeue_file',{'ident':params['dequeue'],'wst':token})
        xml = ET.fromstring(response.content)
        if is_ok(xml):
            popinfo(_addon.getLocalizedString(30106))
        else:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        updateListing=True
    
    response = api('queue',{'wst':token})
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        for file in xml.iter('file'):
            item = todict(file)
            commands = []
            commands.append(( _addon.getLocalizedString(30215), 'Container.Update(' + get_url(action='queue',dequeue=item['ident']) + ')'))
            listitem = tolistitem(item,commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=item['ident'],name=item['name']), listitem, False)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(_handle,updateListing=updateListing)

def toqueue(ident,token):
    response = api('queue_file',{'ident':ident,'wst':token})
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        popinfo(_addon.getLocalizedString(30105))
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)

def history(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \ " + _addon.getLocalizedString(30203))
    token = revalidate()
    updateListing=False
    
    if 'remove' in params:
        remove = params['remove']
        updateListing=True
        response = api('history',{'wst':token})
        xml = ET.fromstring(response.content)
        ids = []
        if is_ok(xml):
            for file in xml.iter('file'):
                if remove == file.find('ident').text:
                    ids.append(file.find('download_id').text)
        else:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        if ids:
            rr = api('clear_history',{'ids[]':ids,'wst':token})
            xml = ET.fromstring(rr.content)
            if is_ok(xml):
                popinfo(_addon.getLocalizedString(30104))
            else:
                popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    
    if 'toqueue' in params:
        toqueue(params['toqueue'],token)
        updateListing=True
    
    response = api('history',{'wst':token})
    xml = ET.fromstring(response.content)
    files = []
    if is_ok(xml):
        for file in xml.iter('file'):
            item = todict(file, ['ended_at', 'download_id', 'started_at'])
            if item not in files:
                files.append(item)
        for file in files:
            commands = []
            commands.append(( _addon.getLocalizedString(30213), 'Container.Update(' + get_url(action='history',remove=file['ident']) + ')'))
            commands.append(( _addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='history',toqueue=file['ident']) + ')'))
            listitem = tolistitem(file, commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=file['ident'],name=file['name']), listitem, False)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(_handle,updateListing=updateListing)
    
def settings(params):
    _addon.openSettings()
    xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())

def infonize(data,key,process=str,showkey=True,prefix='',suffix='\n'):
    if key in data:
        return prefix + (key.capitalize() + ': ' if showkey else '') + process(data[key]) + suffix
    return ''

def fpsize(fps):
    x = round(float(fps),3)
    if int(x) == x:
       return str(int(x))
    return str(x)
    
def getinfo(ident,wst):
    response = api('file_info',{'ident':ident,'wst': wst})
    xml = ET.fromstring(response.content)
    ok = is_ok(xml)
    if not ok:
        response = api('file_info',{'ident':ident,'wst': wst, 'maybe_removed':'true'})
        xml = ET.fromstring(response.content)
        ok = is_ok(xml)
    if ok:
        return xml
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return None

def info(params):
    xbmc.log(f'PARAMS: {params}', level=xbmc.LOGINFO)
    token = revalidate()
    xml = getinfo(params['ident'],token)
    
    if xml is not None:
        info = todict(xml)
        text = ''
        text += infonize(info, 'name')
        text += infonize(info, 'size', sizelize)
        text += infonize(info, 'type')
        text += infonize(info, 'width')
        text += infonize(info, 'height')
        text += infonize(info, 'format')
        text += infonize(info, 'fps', fpsize)
        text += infonize(info, 'bitrate', lambda x:sizelize(x,['bps','Kbps','Mbps','Gbps']))
        if 'video' in info and 'stream' in info['video']:
            streams = info['video']['stream']
            if isinstance(streams, dict):
                streams = [streams]
            for stream in streams:
                text += 'Video stream: '
                text += infonize(stream, 'width', showkey=False, suffix='')
                text += infonize(stream, 'height', showkey=False, prefix='x', suffix='')
                text += infonize(stream,'format', showkey=False, prefix=', ', suffix='')
                text += infonize(stream,'fps', fpsize, showkey=False, prefix=', ', suffix='')
                text += '\n'
        if 'audio' in info and 'stream' in info['audio']:
            streams = info['audio']['stream']
            if isinstance(streams, dict):
                streams = [streams]
            for stream in streams:
                text += 'Audio stream: '
                text += infonize(stream, 'format', showkey=False, suffix='')
                text += infonize(stream,'channels', prefix=', ', showkey=False, suffix='')
                text += infonize(stream,'bitrate', lambda x:sizelize(x,['bps','Kbps','Mbps','Gbps']), prefix=', ', showkey=False, suffix='')
                text += '\n'
        text += infonize(info, 'removed', lambda x:'Yes' if x=='1' else 'No')
        xbmc.log(f'PARAMS: {params}', level=xbmc.LOGDEBUG)
        xbmcgui.Dialog().textviewer(_addon.getAddonInfo('name'), text)

def getlink(ident,wst,dtype='video_stream'):
    #uuid experiment
    duuid = _addon.getSetting('duuid')
    if not duuid:
        duuid = str(uuid.uuid4())
        _addon.setSetting('duuid',duuid)
    data = {'ident':ident,'wst': wst,'download_type':dtype,'device_uuid':duuid}
    #TODO password protect
    #response = api('file_protected',data) #protected
    #xml = ET.fromstring(response.content)
    #if is_ok(xml) and xml.find('protected').text != 0:
    #    pass #ask for password
    response = api('file_link',data)
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        return xml.find('link').text
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return None

def play(params):
    token = revalidate()
    link = getlink(params['ident'],token)
    if link is not None:
        # Nová logika pro uložení do historie
        media_id = params.get('media_id')
        media_type = params.get('media_type')
        if media_id and media_type:
            try:
                _session.post(f"{BACKEND_URL}/Database/history", json={"mediaId": media_id, "mediaType": media_type})
            except Exception as e:
                xbmc.log(f"Chyba při ukládání do historie: {e}", level=xbmc.LOGERROR)

        #headers experiment
        headers = _session.headers
        if headers:
            headers.update({'Cookie':'wst='+token})
            link = link + '|' + urlencode(headers)
        listitem = xbmcgui.ListItem(label=params['name'],path=link)
        listitem.setProperty('mimetype', 'application/octet-stream')
        xbmcplugin.setResolvedUrl(_handle, True, listitem)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())

def join(path, file):
    if path.endswith('/') or path.endswith('\\'):
        return path + file
    else:
        return path + '/' + file

def download(params):
    token = revalidate()
    where = _addon.getSetting('dfolder')
    if not where or not xbmcvfs.exists(where):
        popinfo('set folder!', sound=True)#_addon.getLocalizedString(30101)
        _addon.openSettings()
        return
        
    local = os.path.exists(where)
        
    normalize = 'true' == _addon.getSetting('dnormalize')
    notify = 'true' == _addon.getSetting('dnotify')
    every = _addon.getSetting('dnevery')
    try:
        every = int(re.sub(r'[^\d]+', '', every))
    except:
        every = 10
        
    try:
        link = getlink(params['ident'],token,'file_download')
        info = getinfo(params['ident'],token)
        name = info.find('name').text
        if normalize:
            name = unidecode.unidecode(name)
        bf = io.open(os.path.join(where,name), 'wb') if local else xbmcvfs.File(join(where,name), 'w')
        response = _session.get(link, stream=True)
        total = response.headers.get('content-length')
        if total is None:
            popinfo(_addon.getLocalizedString(30301) + name, icon=xbmcgui.NOTIFICATION_WARNING, sound=True)
            bf.write(response.content)
        elif not notify:
            popinfo(_addon.getLocalizedString(30302) + name)
            bf.write(response.content)
        else:
            popinfo(_addon.getLocalizedString(30302) + name)
            dl = 0
            total = int(total)
            pct = total / 100
            lastpop=0
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                bf.write(data)
                done = int(dl / pct)
                if done % every == 0 and lastpop != done:
                    popinfo(str(done) + '% - ' + name)
                    lastpop = done
        bf.close()
        popinfo(_addon.getLocalizedString(30303) + name, sound=True)
    except Exception as e:
        #TODO - remove unfinished file?
        traceback.print_exc()
        popinfo(_addon.getLocalizedString(30304) + name, icon=xbmcgui.NOTIFICATION_ERROR, sound=True)

def loaddb(dbdir,file):
    try:
        data = {}
        with io.open(os.path.join(dbdir, file), 'r', encoding='utf8') as file:
            fdata = file.read()
            file.close()
            try:
                data = json.loads(fdata, "utf-8")['data']
            except TypeError:
                data = json.loads(fdata)['data']
        return data
    except Exception as e:
        traceback.print_exc()
        return {}

def db(params):
    token = revalidate()
    updateListing=False
    dbdir = os.path.join(_profile,'db')
    if not os.path.exists(dbdir):
        link = getlink(BACKUP_DB,token)
        dbfile = os.path.join(_profile,'db.zip')
        with io.open(dbfile, 'wb') as bf:
            response = _session.get(link, stream=True)
            bf.write(response.content)
            bf.flush()
            bf.close()
        with zipfile.ZipFile(dbfile, 'r') as zf:
            zf.extractall(_profile)
        os.unlink(dbfile)
    
    if 'toqueue' in params:
        toqueue(params['toqueue'],token)
        updateListing=True
    
    if 'file' in params and 'key' in params:
        data = loaddb(dbdir,params['file'])
        item = next((x for x in data if x['id'] == params['key']), None)
        if item is not None:
            for stream in item['streams']:
                commands = []
                commands.append(( _addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='db',file=params['file'],key=params['key'],toqueue=stream['ident']) + ')'))
                listitem = tolistitem({'ident':stream['ident'],'name':stream['quality'] + ' - ' + stream['lang'] + stream['ainfo'],'sizelized':stream['size']},commands)
                xbmcplugin.addDirectoryItem(_handle, get_url(action='play',ident=stream['ident'],name=item['title']), listitem, False)
    elif 'file' in params:
        data = loaddb(dbdir,params['file'])
        for item in data:
            listitem = xbmcgui.ListItem(label=item['title'])
            if 'plot' in item:
                listitem.setInfo('video', {'title': item['title'],'plot': item['plot']})
            xbmcplugin.addDirectoryItem(_handle, get_url(action='db',file=dbfile), listitem, True)
    else:
        if os.path.exists(dbdir):
            dbfiles = [f for f in os.listdir(dbdir) if os.path.isfile(os.path.join(dbdir, f))]
            for dbfile in dbfiles:
                listitem = xbmcgui.ListItem(label=os.path.splitext(dbfile)[0])
                xbmcplugin.addDirectoryItem(_handle, get_url(action='db',file=dbfile), listitem, True)
    xbmcplugin.addSortMethod(_handle,xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)

def menu():
    """Opravené hlavní menu s požadovaným pořadím a názvy."""
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name'))

    # 1. Vyhledávání v mé databázi - NOVÝ NÁZEV
    list_item = xbmcgui.ListItem(label='Vyhledávání v mé databázi')
    list_item.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='search_my_db'), list_item, True)

    # 2. Vyhledávání Webshare - NOVÝ NÁZEV
    list_item = xbmcgui.ListItem(label='Vyhledávání na Webshare')
    list_item.setArt({'icon': 'DefaultFolder.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='search'), list_item, True)
    
    # 3. Filmy
    list_item = xbmcgui.ListItem(label='Filmy')
    list_item.setArt({'icon': 'DefaultMovies.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='movies_menu'), list_item, True)

    # 4. Seriály
    list_item = xbmcgui.ListItem(label='Seriály')
    list_item.setArt({'icon': 'DefaultTVShows.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='shows_menu'), list_item, True)
    
    # NOVÁ SLOŽKA V HLAVNÍM MENU: TV tipy dne z ČSFD (POSLEDNÍ před Nastavením)
    list_item = xbmcgui.ListItem(label='TV tipy dne z ČSFD')
    list_item.setArt({'icon': ICON_CHANNELS}) # OPRAVENÁ IKONA
    xbmcplugin.addDirectoryItem(_handle, get_url(action='tv_tips_menu'), list_item, True)


    # 5. Nastavení doplňku (Poslední)
    list_item = xbmcgui.ListItem(label=_addon.getLocalizedString(30204)) # Popisek "Nastavení"
    list_item.setArt({'icon': 'DefaultAddonService.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='settings'), list_item, False)

    xbmcplugin.endOfDirectory(_handle)

def movies_menu():
    xbmcplugin.setPluginCategory(_handle, 'Filmy')
    
    # 1. Stávající podkategorie (Historie, Vše, Žánry)
    list_item = xbmcgui.ListItem(label='Historie sledování')
    list_item.setArt({'icon': 'DefaultVideo.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='list_watched_movies'), list_item, True)

    list_item = xbmcgui.ListItem(label='Vše')
    list_item.setArt({'icon': 'DefaultMovies.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='list_all_my_movies'), list_item, True)

    list_item = xbmcgui.ListItem(label='Žánry')
    list_item.setArt({'icon': 'DefaultGenre.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='list_movie_genres'), list_item, True)
    
    # NOVÁ SLOŽKA: Nejlépe hodnocené ČSFD (POSLEDNÍ V POŘADÍ)
    list_item = xbmcgui.ListItem(label='Nejlépe hodnocené ČSFD')
    list_item.setArt({'icon': ICON_FAVOURITES}) # OPRAVENÁ IKONA
    xbmcplugin.addDirectoryItem(_handle, get_url(action='show_top_movies_from_db'), list_item, True)

    xbmcplugin.endOfDirectory(_handle)

def shows_menu():
    xbmcplugin.setPluginCategory(_handle, 'Seriály')
    
    # 1. Stávající podkategorie (Historie, Vše, Žánry)
    list_item = xbmcgui.ListItem(label='Historie sledování')
    list_item.setArt({'icon': 'DefaultVideo.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='list_watched_shows'), list_item, True)

    list_item = xbmcgui.ListItem(label='Vše')
    list_item.setArt({'icon': 'DefaultTVShows.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='list_all_my_shows'), list_item, True)
    
    list_item = xbmcgui.ListItem(label='Žánry')
    list_item.setArt({'icon': 'DefaultGenre.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='list_show_genres'), list_item, True)
    
    # NOVÁ SLOŽKA: Nejlépe hodnocené ČSFD (POSLEDNÍ V POŘADÍ)
    list_item = xbmcgui.ListItem(label='Nejlépe hodnocené ČSFD')
    list_item.setArt({'icon': ICON_FAVOURITES}) # OPRAVENÁ IKONA
    xbmcplugin.addDirectoryItem(_handle, get_url(action='show_top_shows_from_db'), list_item, True)

    xbmcplugin.endOfDirectory(_handle)

def list_watched_movies():
    xbmcplugin.setPluginCategory(_handle, 'Historie sledování filmů')
    try:
        response = _session.get(f"{BACKEND_URL}/Database/history/movies")
        response.raise_for_status()
        movies = response.json()
        
        # --- LOGIKA PRO UNIKÁTNÍ ZÁZNAMY ---
        unique_movies = {}
        for movie in movies:
            movie_id = movie.get('id')
            # Záznamy v historii nemají přímo 'id' filmu, ale 'mediaId'. Budeme tedy filtrovat podle 'mediaId'.
            media_id = movie.get('mediaId', movie.get('id'))
            
            # Pouze pokud dané ID ještě nebylo přidáno (odstraní duplicity)
            if media_id not in unique_movies: 
                 unique_movies[media_id] = movie
        
        filtered_movies = list(unique_movies.values())
        # --- KONEC NOVÉ LOGIKY ---

        if not filtered_movies:
            xbmcgui.Dialog().ok("Historie je prázdná", "Žádné filmy nebyly zatím sledovány.")
        else:
            for movie in filtered_movies:
                _add_movie_list_item(movie, is_history=True)

    except Exception as e:
        xbmc.log(f"Chyba při načítání historie filmů: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst historii filmů.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)


def list_watched_shows():
    xbmcplugin.setPluginCategory(_handle, 'Historie sledování seriálů')
    try:
        response = _session.get(f"{BACKEND_URL}/Database/history/shows")
        response.raise_for_status()
        shows = response.json()
        
        # --- NOVÁ LOGIKA PRO UNIKÁTNÍ ZÁZNAMY ---
        unique_shows = {}
        for show in shows:
            media_id = show.get('mediaId', show.get('id'))
            
            # Pouze pokud dané ID ještě nebylo přidáno (odstraní duplicity)
            if media_id not in unique_shows:
                unique_shows[media_id] = show
        
        filtered_shows = list(unique_shows.values())
        # --- KONEC NOVÉ LOGIKY ---

        if not filtered_shows:
            xbmcgui.Dialog().ok("Historie je prázdná", "Žádné seriály nebyly zatím sledovány.")
        else:
            for show in filtered_shows:
                _add_show_list_item(show, is_history=True)
    
    except Exception as e:
        xbmc.log(f"Chyba při načítání historie seriálů: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst historii seriálů.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)

def list_movie_genres():
    xbmcplugin.setPluginCategory(_handle, 'Žánry filmů')
    try:
        response = _session.get(f"{BACKEND_URL}/Movies")
        response.raise_for_status()
        movies = response.json()
        
        genres_dict = defaultdict(list)
        for movie in movies:
            genres_data = movie.get('genres', [])
            if isinstance(genres_data, str):
                genre_list = [g.strip() for g in genres_data.split('/')]
            else:
                genre_list = [g['name'] for g in genres_data]
            
            for genre in genre_list:
                genres_dict[genre].append(movie)

        for genre, movies_list in sorted(genres_dict.items()):
            list_item = xbmcgui.ListItem(label=genre)
            url = get_url(action='list_movies_by_genre', genre=genre)
            xbmcplugin.addDirectoryItem(_handle, url=url, listitem=list_item, isFolder=True)

    except Exception as e:
        xbmc.log(f"Chyba při načítání žánrů filmů: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst žánry filmů.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)

def list_show_genres():
    xbmcplugin.setPluginCategory(_handle, 'Žánry seriálů')
    try:
        response = _session.get(f"{BACKEND_URL}/Shows")
        response.raise_for_status()
        shows = response.json()
        
        genres_dict = defaultdict(list)
        for show in shows:
            genres_data = show.get('genres', [])
            if isinstance(genres_data, str):
                genre_list = [g.strip() for g in genres_data.split('/')]
            else:
                genre_list = [g['name'] for g in genres_data]
            
            for genre in genre_list:
                genres_dict[genre].append(show)

        for genre, shows_list in sorted(genres_dict.items()):
            list_item = xbmcgui.ListItem(label=genre)
            url = get_url(action='list_shows_by_genre', genre=genre)
            xbmcplugin.addDirectoryItem(_handle, url=url, listitem=list_item, isFolder=True)

    except Exception as e:
        xbmc.log(f"Chyba při načítání žánrů seriálů: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst žánry seriálů.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)

def list_movies_by_genre(params):
    genre = params.get('genre')
    xbmcplugin.setPluginCategory(_handle, f'Filmy - {genre}')
    try:
        response = _session.get(f"{BACKEND_URL}/Movies")
        response.raise_for_status()
        movies = response.json()
        
        for movie in movies:
            genres_data = movie.get('genres', [])
            if isinstance(genres_data, str) and genre in genres_data:
                _add_movie_list_item(movie)
            elif isinstance(genres_data, list) and any(g['name'] == genre for g in genres_data):
                _add_movie_list_item(movie)

    except Exception as e:
        xbmc.log(f"Chyba při načítání filmů podle žánru: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst filmy pro žánr {genre}.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)

def list_shows_by_genre(params):
    genre = params.get('genre')
    xbmcplugin.setPluginCategory(_handle, f'Seriály - {genre}')
    try:
        response = _session.get(f"{BACKEND_URL}/Shows")
        response.raise_for_status()
        shows = response.json()
        
        for show in shows:
            genres_data = show.get('genres', [])
            if isinstance(genres_data, str) and genre in genres_data:
                _add_show_list_item(show)
            elif isinstance(genres_data, list) and any(g['name'] == genre for g in genres_data):
                _add_show_list_item(show)

    except Exception as e:
        xbmc.log(f"Chyba při načítání seriálů podle žánru: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst seriály pro žánr {genre}.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)

def _add_movie_list_item(movie, is_history=False, rank=None, rank_prefix=None):
    links = movie.get('links', [])
    title = movie.get('title')
    genres_data = movie.get('genres', [])
    if isinstance(genres_data, str):
        genres_str = genres_data
    else:
        genres = [g['name'] for g in genres_data]
        genres_str = ' / '.join(genres) if genres else 'Neznámý'
    
    year = movie.get('releaseYear', '????')
    runtime_minutes = movie.get('runtime', 0)
    duration_str = "????"
    if runtime_minutes > 0:
        hours = runtime_minutes // 60
        minutes = runtime_minutes % 60
        duration_str = f"{hours}h:{minutes:02d}m" if hours > 0 else f"{minutes}m"
    
    # ZMĚNA: Formát číslování a prefixu
    if rank_prefix:
        label_prefix = f"{rank_prefix}"
    elif rank is not None:
        label_prefix = f"{rank}. "
    else:
        label_prefix = "CZ - "
        
    label = f"{label_prefix}{title} ({year}) | {genres_str}"
    
    if is_history:
        label = f"[Historie] {label}"
    
    list_item = xbmcgui.ListItem(label=label)
    list_item.setLabel2(f"{duration_str}")

    info = {
        'mediatype': 'movie',
        'title': title,
        'plot': movie.get('overview')
    }
    if year != '????': info['year'] = year
    if isinstance(genres_data, str): info['genre'] = genres_data
    elif genres_data: info['genre'] = genres
    if runtime_minutes > 0: info['duration'] = runtime_minutes * 60

    list_item.setInfo('video', info)
    
    poster = movie.get('posterPath')
    if poster:
        poster_url = f"https://image.tmdb.org/t/p/w500{poster}"
        list_item.setArt({'icon': poster_url, 'thumb': poster_url, 'poster': poster_url})
    
    if len(links) == 1:
        playable_url = get_url(action='play', ident=links[0]['fileIdent'], name=title, media_id=movie['id'], media_type='Movie')
        list_item.setProperty('IsPlayable', 'true')
        is_folder = False
    else:
        playable_url = get_url(action='select_link', links=json.dumps(links), name=title, media_id=movie['id'], media_type='Movie')
        list_item.setProperty('IsPlayable', 'true')
        is_folder = False
    xbmcplugin.addDirectoryItem(_handle, url=playable_url, listitem=list_item, isFolder=is_folder)

def _add_show_list_item(show, is_history=False, rank=None, rank_prefix=None):
    title = show.get('title')
    genres_data = show.get('genres', [])
    if isinstance(genres_data, str):
        genres_str = genres_data
    else:
        genres = [g['name'] for g in genres_data]
        genres_str = ' / '.join(genres) if genres else "Neznámý"

    # ZMĚNA: Formát číslování
    if rank_prefix:
        label_prefix = f"{rank_prefix}"
    elif rank is not None:
        label_prefix = f"{rank}. "
    else:
        label_prefix = "CZ - "
        
    label = f"{label_prefix}{title} | {genres_str}"
    
    if is_history:
        label = f"[Historie] {label}"
        
    list_item = xbmcgui.ListItem(label=label)
    info = {'plot': show.get('overview'), 'mediatype': 'tvshow', 'title': title}
    if isinstance(genres_data, str): info['genre'] = genres_data
    elif genres_data: info['genre'] = genres
    list_item.setInfo('video', info)
    
    poster = show.get('posterPath')
    if poster:
        poster_url = f"https://image.tmdb.org/t/p/w500{poster}"
        list_item.setArt({'thumb': poster_url, 'icon': poster_url, 'poster': poster_url})
    
    url = get_url(action='list_seasons', show_id=show.get('id'))
    xbmcplugin.addDirectoryItem(_handle, url=url, listitem=list_item, isFolder=True)


def list_all_my_movies():
    xbmcplugin.setContent(_handle, 'movies')
    xbmcplugin.setPluginCategory(_handle, 'Všechny filmy')
    
    try:
        response = _session.get(f"{BACKEND_URL}/Movies")
        response.raise_for_status()
        movies = response.json()

        for movie in movies:
            _add_movie_list_item(movie)
            
    except Exception as e:
        xbmc.log(f"Chyba ve funkci list_all_my_movies: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst filmy.\nDetail: {e}")
    
    xbmcplugin.endOfDirectory(_handle)
    xbmc.executebuiltin('Container.SetViewMode(50)')

def list_all_my_shows():
    xbmcplugin.setPluginCategory(_handle, 'Všechny seriály')
    try:
        response = _session.get(f"{BACKEND_URL}/Shows")
        response.raise_for_status()
        shows = response.json()

        for show in shows:
            _add_show_list_item(show)

    except Exception as e:
        xbmc.log(f"Chyba ve funkci list_all_my_shows: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst seriály.\nDetail: {e}")
    xbmcplugin.endOfDirectory(_handle)

def list_seasons(params):
    show_id = params.get('show_id')

    xbmcplugin.setContent(_handle, 'seasons')
    
    try:
        response = _session.get(f"{BACKEND_URL}/Shows/{show_id}")
        response.raise_for_status()
        show_details = response.json()
        
        # Získání dostupných jazyků pro seriál
        available_languages = set()
        for season in show_details.get('seasons', []):
            if 'episodes' in season:
                for episode in season['episodes']:
                    if 'links' in episode:
                        for link in episode['links']:
                            ident = link.get('fileIdent')
                            if ident:
                                xml_info = getinfo(ident, revalidate())
                                if xml_info:
                                    info = todict(xml_info)
                                    if 'audio' in info and 'stream' in info['audio']:
                                        audio_streams = info['audio']['stream']
                                        if isinstance(audio_streams, dict):
                                            audio_streams = [audio_streams]
                                        for stream in audio_streams:
                                            lang = stream.get('language', '')
                                            if lang:
                                                available_languages.add(lang.upper())

        languages_str = ' | '.join(sorted(list(available_languages))) if available_languages else 'Neznámý'
        xbmcplugin.setPluginCategory(_handle, f"Jazyky: ({languages_str})")
        
        for season in show_details.get('seasons', []):
            season_number = season.get('seasonNumber')
            if season_number == 0: continue

            year = season.get('releaseYear', '????')
            title = f"Série {season_number}"
            
            # Vylepšený popisek pro sezóny
            label = f"{title} ({year})" if year != '????' else title
            list_item = xbmcgui.ListItem(label=label)
            info = {'title': title, 'mediatype': 'season', 'tvshowtitle': show_details.get('title')}
            list_item.setInfo('video', info)

            poster = season.get('posterPath') or show_details.get('posterPath')
            if poster:
                 poster_url = f"https://image.tmdb.org/t/p/w500{poster}"
                 list_item.setArt({'icon': poster_url, 'thumb': poster_url, 'poster': poster_url})

            url = get_url(action='list_episodes', show_id=show_id, season_number=season_number)
            xbmcplugin.addDirectoryItem(_handle, url=url, listitem=list_item, isFolder=True)
            
    except Exception as e:
        xbmc.log(f"Chyba ve funkci list_seasons: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst sezóny.\nDetail: {e}")
        
    xbmcplugin.endOfDirectory(_handle)
    xbmc.executebuiltin('Container.SetViewMode(50)')

def list_episodes(params):
    show_id = params.get('show_id')
    season_number_str = params.get('season_number')
    if not season_number_str:
        popinfo("Chyba: Chybí číslo sezóny.", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    season_number = int(season_number_str)

    xbmcplugin.setContent(_handle, 'movies')
    
    try:
        response = _session.get(f"{BACKEND_URL}/Shows/{show_id}")
        response.raise_for_status()
        show_details = response.json()
        
        xbmcplugin.setPluginCategory(_handle, f"{show_details.get('title')} - Série {season_number}")
        target_season = next((s for s in show_details.get('seasons', []) if int(s.get('seasonNumber', -1)) == season_number), None)

        if target_season:
            for episode in target_season.get('episodes', []):
                links = episode.get('links', [])
                if not links: continue
                
                episode_title = episode.get('title')
                episode_number = episode.get('episodeNumber')
                
                # Získání délky epizody pro zobrazení
                runtime_minutes = episode.get('runtime')
                duration_str = "???"
                if runtime_minutes and runtime_minutes > 0:
                    runtime_minutes = int(runtime_minutes)
                    hours = runtime_minutes // 60
                    minutes = runtime_minutes % 60
                    duration_str = f"{hours}h:{minutes:02d}m" if hours > 0 else f"{minutes}m"

                # Vylepšený popisek pro epizodu
                label = f"CZ - {episode_number}. {episode_title}"
                
                list_item = xbmcgui.ListItem(label=label)
                list_item.setLabel2(f"{duration_str}")

                info = {
                    'mediatype': 'episode', 'title': episode_title,
                    'plot': episode.get('overview'), 'tvshowtitle': show_details.get('title'),
                    'season': season_number, 'episode': episode_number
                }

                if runtime_minutes > 0:
                    info['duration'] = runtime_minutes * 60

                list_item.setInfo('video', info)
                
                still = episode.get('stillPath')
                if still:
                    still_url = f"https://image.tmdb.org/t/p/w500{still}"
                    list_item.setArt({'icon': still_url, 'thumb': still_url})

                if len(links) == 1:
                    playable_url = get_url(action='play', ident=links[0]['fileIdent'], name=episode_title, media_id=show_id, media_type='Show')
                    list_item.setProperty('IsPlayable', 'true')
                    is_folder = False
                else:
                    playable_url = get_url(action='select_link', links=json.dumps(links), name=episode_title, media_id=show_id, media_type='Show')
                    list_item.setProperty('IsPlayable', 'true')
                    is_folder = False

                xbmcplugin.addDirectoryItem(_handle, url=playable_url, listitem=list_item, isFolder=is_folder)
        else:
            popinfo(f"Nenalezena sezóna číslo {season_number} v datech z API.", icon=xbmcgui.NOTIFICATION_WARNING)
            
    except Exception as e:
        xbmc.log(f"Chyba ve funkci list_episodes: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst epizody.\nDetail: {e}")
        
    xbmcplugin.endOfDirectory(_handle)
    xbmc.executebuiltin('Container.SetViewMode(50)')

def search_my_db():
    query = ask(None)
    if not query: return

    xbmcplugin.setPluginCategory(_handle, f'Hledám v mé DB: {query}')
    try:
        response = _session.get(f"{BACKEND_URL}/Search", params={'query': query})
        response.raise_for_status()
        results = response.json()
        
        if not results: 
            popinfo("Nebyly nalezeny žádné výsledky.")
            xbmcplugin.endOfDirectory(_handle)
            return
        
        for item in results:
            # Oprava chyby: Zajištění, že položka má základní klíče
            if not item.get('id') or not item.get('type') or not item.get('title'):
                xbmc.log(f"Search result item missing critical key: {item}", xbmc.LOGWARNING)
                continue

            if item.get('type') == 'Movie':
                _add_movie_list_item(item) # Využijeme existující funkci pro filmy
            elif item.get('type') == 'Show':
                _add_show_list_item(item)  # Využijeme existující funkci pro seriály
            # Ostatní typy se ignorují
            
    except Exception as e:
        xbmc.log(f"Chyba při vyhledávání v DB: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se provést vyhledávání.\nDetail: {e}")
        
    xbmcplugin.endOfDirectory(_handle)
    xbmc.executebuiltin('Container.SetViewMode(50)')

def search_webshare(params):
    search(params)
    
# ==============================================================================
# === FUNKCE PRO VLASTNÍ DIALOG ===
# ==============================================================================

def select_link(params):
    links_json = params.get('links', '[]')
    title = params.get('name', 'Video')
    media_id = params.get('media_id')
    media_type = params.get('media_type')

    links = json.loads(links_json)
    if not links:
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return
        
    options = []
    # Získání doplňujících informací o souborech
    token = revalidate()
    for link in links:
        quality = link.get('quality', 'Neznámá kvalita')
        ident = link.get('fileIdent')
        
        try:
            # Načtení informací o souboru z Webshare API
            xml_info = getinfo(ident, token)
            if xml_info:
                info = todict(xml_info)
                size = sizelize(info.get('size', '0'))
                bitrate = sizelize(info.get('bitrate', '0'), ['bps', 'Kbps', 'Mbps', 'Gbps'])
                
                # Získání informací o audio streamech
                audio_streams_info = ""
                if 'audio' in info and 'stream' in info['audio']:
                    audio_streams = info['audio']['stream']
                    if isinstance(audio_streams, dict):
                        audio_streams = [audio_streams]
                    audio_info_list = []
                    for stream in audio_streams:
                        lang = stream.get('language', '')
                        audio_info_list.append(lang.upper() if lang else 'Neznámý')
                    audio_streams_info = f"Zvuk: ({' | '.join(audio_info_list)})" if audio_info_list else ""

                # Získání informací o titulcích
                sub_info_str = ""
                if 'subtitles' in info and 'subtitles' in info['subtitles']:
                    subs = info['subtitles']['subtitles']
                    if subs:
                        sub_list = subs.split(',')
                        sub_info_str = f"Tit: ({', '.join(sub_list)})"
                
                # Sestavení jednoho řádku s kompletními informacemi
                full_info = [
                    f"{quality}",
                    f"| {size} |",
                    f"({bitrate})",
                    audio_streams_info,
                ]
                
                options_str = ' | '.join([i for i in full_info if i.strip() != ""])
                
                if sub_info_str:
                    options_str = f"{options_str} | {sub_info_str}"
                    
                options.append(options_str)
            else:
                options.append(f"{quality} - Neznámé info")
        except Exception as e:
            options.append(f"{quality} - Chyba načítání")
            xbmc.log(f"Chyba při načítání informací o odkazu {ident}: {e}", xbmc.LOGERROR)

    dialog = xbmcgui.Dialog()
    selected_index = dialog.select(f"Vyberte kvalitu pro: {title}", options)
    
    if selected_index != -1:
        selected_link = links[selected_index]
        ident = selected_link.get('fileIdent')
        
        play(params={'ident': ident, 'name': title, 'media_id': media_id, 'media_type': media_type})
    else:
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())

# ==============================================================================
# === NOVÉ FUNKCE PRO ZOBRAZENÍ TOP ČSFD Z DB ===
# ==============================================================================

def get_movies_from_db():
    try:
        response = _session.get(f"{BACKEND_URL}/Movies")
        response.raise_for_status()
        movies = response.json()
        # Vytvoříme slovník pro rychlé vyhledávání podle normalizovaného názvu
        # Pro zjednodušení a spolehlivost porovnávání použijeme normalizaci,
        # kterou předpokládáme v backendu (unidecode, bez mezer/interpunkce).
        movie_dict = {normalize_title(m.get('title')): m for m in movies if m.get('title')}
        return movie_dict
    except Exception as e:
        xbmc.log(f"Chyba při načítání filmů z DB: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst filmy z databáze.\nDetail: {e}")
        return {}

def get_shows_from_db():
    try:
        response = _session.get(f"{BACKEND_URL}/Shows")
        response.raise_for_status()
        shows = response.json()
        # Vytvoříme slovník pro rychlé vyhledávání podle normalizovaného názvu
        # Pro zjednodušení a spolehlivost porovnávání použijeme normalizaci,
        # kterou předpokládáme v backendu (unidecode, bez mezer/interpunkce).
        show_dict = {normalize_title(s.get('title')): s for s in shows if s.get('title')}
        return show_dict
    except Exception as e:
        xbmc.log(f"Chyba při načítání seriálů z DB: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst seriály z databáze.\nDetail: {e}")
        return {}
        
def get_csfd_titles_list(url):
    """
    Spolehlivá funkce pro získání seřazeného seznamu titulů z ČSFD pomocí vestavěných knihoven KODI (requests/re).
    """
    try:
        # Používáme knihovnu requests
        response = _session.get(url)
        response.raise_for_status()
        html = response.text
        
        # POUŽITÍ RegEx pro spolehlivou extrakci titulů z HTML
        
        if "televize" in url:
             # --- LOGIKA PRO TV TIPY (FINÁLNÍ OPRAVA) ---
             # RegEx najde název (z titulu odkazu)
             program_items = re.findall(r'<a href="/(film|serial)/[^/]+/"[^>]*>(.*?)</a>', html, re.DOTALL)
             
             clean_titles = []
             for media_type, title_raw in program_items:
                 # 1. Čištění titulku od HTML a rušivých prvků
                 title = re.sub(r'<[^>]+>', '', title_raw).strip()
                 
                 # 2. Vytvoření čistého názvu pro porovnání s DB (odstraní rok/kanál/extra text)
                 clean_title = re.sub(r'\s*\(\d{4}\)', '', title).strip() 
                 clean_title = clean_title.split('|')[0].strip()
                 
                 if clean_title and clean_title not in clean_titles: # Deduplikace
                    clean_titles.append(clean_title) 
             
             # Vrátíme pole unikátních, očištěných, čistých názvů.
             return clean_titles
             
        else:
             # --- LOGIKA PRO ŽEBŘÍČKY ---
             # Hledáme: title="..." class="film-title-name"
             titles = re.findall(r'title="([^"]+)" class="film-title-name"', html)
             return titles # Vrací seřazený list titulů

    except Exception as e:
        xbmc.log(f"Chyba při volání/scrapingu ČSFD: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Scraperu", f"Nepodařilo se stáhnout žebříček z ČSFD.\nDetail: {e}")
        return []

def normalize_title(title):
    """Zjednodušená normalizace pro porovnávání."""
    if not title: return ''
    normalized = unidecode.unidecode(title).lower()
    # Ponecháme pouze alfanumerické znaky (odstraní mezery, interpunkci atd.)
    return re.sub(r'[^a-z0-9]', '', normalized)

def show_top_movies_from_db(params):
    xbmcplugin.setPluginCategory(_handle, 'Nejlépe hodnocené filmy ČSFD (Vaše DB)')
    
    CSFD_TOP_URL = "https://www.csfd.cz/zebricky/filmy/nejlepsi/"
    
    try:
        # 1. Získáme všechny filmy z naší databáze do slovníku
        db_movies = get_movies_from_db()

        # 2. Získáme seřazený seznam titulů z ČSFD (scraping)
        csfd_titles = get_csfd_titles_list(CSFD_TOP_URL)
        
        found_count = 0
        
        # 3. Procházíme seřazený žebříček ČSFD a hledáme shody v naší DB
        for i, csfd_title in enumerate(csfd_titles): # Používáme i pro číslování
            normalized_csfd_title = normalize_title(csfd_title)
            
            if normalized_csfd_title in db_movies:
                movie = db_movies[normalized_csfd_title]
                _add_movie_list_item(movie, rank=i + 1) # PŘIDÁNÍ POŘADÍ
                found_count += 1
                
        if found_count == 0:
            xbmcgui.Dialog().ok("Prázdný seznam", "V databázi nebyly nalezeny žádné filmy z TOP žebříčku ČSFD.")

    except Exception as e:
        xbmc.log(f"Chyba při načítání Top ČSFD filmů z DB: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst filmy.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)


def show_top_shows_from_db(params):
    xbmcplugin.setPluginCategory(_handle, 'Nejlépe hodnocené seriály ČSFD (Vaše DB)')
    
    CSFD_TOP_URL = "https://www.csfd.cz/zebricky/serialy/nejlepsi/"
    
    try:
        # 1. Získáme všechny seriály z naší databáze do slovníku
        db_shows = get_shows_from_db()

        # 2. Získáme seřazený seznam titulů z ČSFD (scraping)
        csfd_titles = get_csfd_titles_list(CSFD_TOP_URL)
        
        found_count = 0
        
        # 3. Procházíme seřazený žebříček ČSFD a hledáme shody v naší DB
        for i, csfd_title in enumerate(csfd_titles): # Používáme i pro číslování
            normalized_csfd_title = normalize_title(csfd_title)
            
            if normalized_csfd_title in db_shows:
                show = db_shows[normalized_csfd_title]
                _add_show_list_item(show, rank=i + 1) # PŘIDÁNÍ POŘADÍ
                found_count += 1
                
        if found_count == 0:
            xbmcgui.Dialog().ok("Prázdný seznam", "V databázi nebyly nalezeny žádné seriály z TOP žebříčku ČSFD.")
            
    except Exception as e:
        xbmc.log(f"Chyba při načítání Top ČSFD seriálů z DB: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst seriály.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)


def tv_tips_menu():
    xbmcplugin.setPluginCategory(_handle, 'TV tipy dne z ČSFD')
    CSFD_TV_URL = "https://www.csfd.cz/televize/"
    
    try:
        # 1. Získání všech filmů a seriálů z naší DB do slovníku (jedna operace)
        db_movies = get_movies_from_db()
        db_shows = get_shows_from_db()
        db_content = dict(db_movies, **db_shows) # Sjednotíme filmy a seriály do jednoho slovníku
        
        # 2. Získání TV tipů z ČSFD (upravený scraping: vrací list čistých názvů)
        tv_titles = get_csfd_titles_list(CSFD_TV_URL) 
        
        found_count = 0
        
        # 3. Procházíme TV tipy a hledáme shody v naší DB
        for i, tv_title in enumerate(tv_titles): # PŘIDÁNÍ ČÍSLOVÁNÍ
            normalized_tv_title = normalize_title(tv_title)
            
            if normalized_tv_title in db_content:
                item = db_content[normalized_tv_title]
                
                # Zjištění typu a přidání do seznamu (Filmy mají releaseYear)
                if 'releaseYear' in item: 
                    # Zobrazujeme rank a název
                    _add_movie_list_item(item, rank=i+1) 
                else: 
                    _add_show_list_item(item, rank=i+1)
                    
                found_count += 1
                
        if found_count == 0:
            xbmcgui.Dialog().ok("Prázdný seznam", "V databázi nebyly nalezeny žádné TV tipy, které byste měl uložené.")
            
    except Exception as e:
        xbmc.log(f"Chyba při načítání TV tipů: {traceback.format_exc()}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Chyba Backendu", f"Nepodařilo se načíst TV tipy.\nDetail: {e}")

    xbmcplugin.endOfDirectory(_handle)


# ==============================================================================
# === ROUTER ===
# ==============================================================================

def router(paramstring):
    params = dict(parse_qsl(paramstring))
    action = params.get('action')

    if action == 'search_my_db':
        search_my_db()
    elif action == 'search':
        search(params)
    elif action == 'movies_menu':
        movies_menu()
    elif action == 'shows_menu':
        shows_menu()
    elif action == 'list_watched_movies':
        list_watched_movies()
    elif action == 'list_watched_shows':
        list_watched_shows()
    elif action == 'list_movie_genres':
        list_movie_genres()
    elif action == 'list_show_genres':
        list_show_genres()
    elif action == 'list_movies_by_genre':
        list_movies_by_genre(params)
    elif action == 'list_shows_by_genre':
        list_shows_by_genre(params)
    elif action == 'list_all_my_movies':
        list_all_my_movies()
    elif action == 'list_all_my_shows':
        list_all_my_shows()
    elif action == 'list_seasons':
        list_seasons(params)
    elif action == 'list_episodes':
        list_episodes(params)
    elif action == 'play':
        play(params)
    elif action == 'settings':
        settings(params)
    elif action == 'select_link':
        select_link(params) # Volání upravené funkce
    elif action == 'show_top_movies_from_db': # NOVÁ AKCE
        show_top_movies_from_db(params)
    elif action == 'show_top_shows_from_db': # NOVÁ AKCE
        show_top_shows_from_db(params)
    elif action == 'tv_tips_menu': # NOVÁ AKCE
        tv_tips_menu()
    else:
        menu()

if __name__ == '__main__':
    router(sys.argv[2])