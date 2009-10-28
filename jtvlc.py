#!/usr/bin/env python
#
#       Name:           Jtvlc
#       Author:         Vladislav Yazhbin <vlad@justin.tv>
#       Date:           8/10/2009
#       Version:        0.41
#
#       Description:    Broadcast on Justin.tv with VLC
#
###############################################################################################################

from twisted.internet.protocol import ClientFactory, ServerFactory, DatagramProtocol
from twisted.web.client import getPage
import urllib
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
import sys
import hashlib
import math
import time, datetime
from config import *


class Tool:
    VLC, QTBROADCASTER = range(2)
tool = Tool.VLC

class RTSP_RTP_Client(LineReceiver):                 # for connecting to VideoServer via RTSP over TCP, then sending RTP packets
    class State:
        ANNOUNCE, TRACK_1, TRACK_2, RECORD, STREAM, PAUSE, TEARDOWN = range(7)
    
    def __init__(self):
        self.state = self.State.ANNOUNCE
        self.session = None
        self.nonce = None
        self.seq = 0
        LineReceiver.setRawMode(self)
        global video_server_connection
        video_server_connection = self
            
    def processState(self):
        self.seq+=1
        #if self.seq >= 6:
        #    print "DONE"
        #    return
            
        if self.state == self.State.ANNOUNCE:
            self.sendAnnounce(uri)
        elif self.state == self.State.TRACK_1:
            self.sendSetup('%s/trackid=1' % uri, 'RTP/AVP/TCP;unicast;mode=record;interleaved=0-1')
            if len(rtp_ports) == 1:
                self.state = self.State.TRACK_2
        elif self.state == self.State.TRACK_2:
            self.sendSetup('%s/trackid=2' % uri, 'RTP/AVP/TCP;unicast;mode=record;interleaved=2-3')
        elif self.state == self.State.RECORD:
            self.sendRecord(uri)
            if tool == Tool.VLC:
                startListeningForRDP_UDP()
        elif self.state == self.State.PAUSE:
            self.sendPause(uri)
        elif self.state == self.State.TEARDOWN:
            self.sendTeardown(uri)
            
    def connectionMade(self):
        self.processState()
    
    def datagramReceived(self, datagram, address):
        self.dataReceived(self, datagram)
        
    def dataReceived(self, data):
        for line in data.split('\r\n'):
            self.lineReceived(line)
        self.processState()
         
    def lineReceived(self, line):  
        writeSecretDebug("receive VideoServer:" + line)
        self.session = self.readSession(line, self.session)
        self.nonce = self.readVariable(line, self.nonce, 'www-authenticate', 'nonce')
        if line == 'RTSP/1.0 200 OK':
            self.state += 1
        elif line == 'RTSP/1.0 401 Unauthorized' and self.seq > 1:
            self.state = self.State.TEARDOWN
            reactor.stop()
            error("ERROR 100: your Justin.tv stream key or your username is not correct.  Please see the 'readme.txt' file for help.")
        elif line == 'RTSP/1.0 403 Forbidden':
            self.state = self.State.TEARDOWN
            reactor.stop()
            error("ERROR 101: received a 403 Forbidden error from the server.  Please try again.")
            
    def readSession(self, line, currentvalue):
        if line.strip().lower().startswith('session: '):
            return line.partition(';')[0].partition(': ')[2]
            
    def writeLine(self, line):
        writeSecretDebug("send VideoServer:" + line)
        self.sendLine(line)
    
    def writeData(self, data):
        writeDebug('Sending data to VideoServer...')
        writeSecretDebug("send VideoServer:" + data)
        self.transport.write(data)
        
    def readVariable(self, line, currentvalue, key, subkey = None):
        if line.strip().lower().startswith(key):
            value = line.partition('=')[2]
            if not subkey: return value
            for item in value.split(','):
                if item.lower().strip().startswith(subkey.lower() + '='):
                    return item.partition('=')[2].strip('\"') 
            return currentvalue
        return currentvalue
        
    def sendAnnounce(self, location):
        self.writeLine('ANNOUNCE %s RTSP/1.0' % location)
        self.writeLine('CSeq: %d' % self.seq)
        self.writeLine('Content-Type: application/sdp')
        self.writeLine('User-Agent: %s' % user_agent)
        self.writeAuthorization('ANNOUNCE')
        body = sdp_contents
        self.writeLine('Content-Length: ' + str(len(body) + 2))
        self.writeLine('')
        self.writeLine(body)
        
    def sendSetup(self, track, transport):
        self.sendMethod('SETUP', track, 'Transport: %s' % transport)

    def sendRecord(self, location):
        self.sendMethod('RECORD', location)
        print "Connected to VideoServer successfully."

    def sendPause(self, location):
        self.sendMethod('PAUSE', location)

    def sendTeardown(self, location):
        self.sendMethod('TEARDOWN', location)
        
    def sendMethod(self, method, location, specialHeader = None):
        self.writeLine('%s %s RTSP/1.0' % (method, location))
        self.writeLine('CSeq: %d' % self.seq)
        if specialHeader: self.writeLine(specialHeader)
        self.writeLine('User-Agent: %s' % user_agent)
        self.writeLine('Accept-Language: en-US')
        self.writeAuthorization(method)
        self.writeLine('')

    def writeAuthorization(self, method):
        if self.nonce:
            m = hashlib.md5()
            m.update(streamkey + ':' + realm + ':' + password)
            a1 = m.hexdigest()
            m = hashlib.md5()
            m.update(method + ':' + file)
            a2 = m.hexdigest()
            m = hashlib.md5()
            m.update(a1 + ':' + self.nonce + ':' + a2)
            response = m.hexdigest()
            self.writeLine('Authorization: Digest username="' + streamkey + '", realm="' + realm + '", nonce="' + self.nonce + '", uri="' + file + '", response="' + response + '"')            

class RTP_Server(LineReceiver):                 # for receiving RTP packets from VLC on localhost via TCP
    def __init__(self):
        self.seq = 0
        LineReceiver.setRawMode(self)

    def connectionMade(self):
        print "Receiving video data..."
            
    def dataReceived(self, data):
        writeSecretDebug("receive VLC:" + data)
        if tool == Tool.QTBROADCASTER:
            self.seq+=1
            #self.writeData(data)
            if data.find('RTSP/1.0') > -1:
                self.writeLine('RTSP/1.0 200 OK')
                self.writeLine('Session: 1603617977;timeout=60')
                self.writeLine('Cseq: %d' % self.seq)
                if data.find('SETUP') > -1:
                    #if self.seq == 3:
                    client_ports = data.partition('client_port=')[2].partition(';')[0].split('-')
                    #self.writeLine('Transport: RTP/AVP/TCP;unicast;mode=record;interleaved=0-1')
                    global rtp_ports, rtcp_ports
                    if len(rtp_ports) == 0:
                        server_ports = ['6970', '6971']
                    else:
                        s1 = rtp_ports[len(rtp_ports) - 1] + 2
                        s2 = rtcp_ports[len(rtp_ports) - 1] + 2
                        server_ports = [str(s1), str(s2)]
                    writeSecretDebug("Parsed ports: " + client_ports[0]  + client_ports[1])
                    rtp_ports.append(int(client_ports[0]))
                    rtcp_ports.append(int(client_ports[1]))
                    self.writeLine('Transport: RTP/AVP;unicast;client_port=' + client_ports[0] + '-' + client_ports[1] + ';mode=record;source=127.0.0.1;server_port=' + server_ports[0] + '-' + server_ports[1])
                    #else:
                    #self.writeLine('Transport: RTP/AVP/TCP;unicast;mode=record;interleaved=2-3')
                if data.find('OPTIONS') > -1:
                    self.writeLine('Public: DESCRIBE, SETUP, TEARDOWN, PAUSE, OPTIONS, ANNOUNCE, RECORD, GET_PARAMETER, SET_PARAMETER')
                if data.find('RECORD') > -1:
                    connectToVideoServer()
                self.writeLine('Server: VideoServer Media Server Pro 1.7.0 build11947')
                if data.find('ANNOUNCE') > -1:
                    if data.find('Content-Length: ') > -1:
                        global sdp_contents
                        sdp_contents = data.partition('Content-Length: ')[2].partition("\r\n\r\n")[2]
                        sdp_contents = sdp_contents.rpartition("\r\n")[0]
                        #print "SDP CONTENTS: **" + sdp_contents + "**"
            
                self.writeLine('')
                self.writeLine('')
            else:       #forward non-RTSP packets (e.g. RTP)
                video_server_connection.writeData(data)
        #elif tool == Tool.VLC:
        #    video_server_connection.writeData(data)
        #elif tool == Tool.VLC:
            
    def writeData(self, data): 
        writeSecretDebug("send VLC:" + data)
        self.transport.write(data)
        
    def writeLine(self, line):
        writeSecretDebug("send VLC:" + line)
        self.sendLine(line)
        
class VideoServerClientFactory(ClientFactory):
    protocol = RTSP_RTP_Client

    def clientConnectionFailed(self, connector, reason):
        print reason.getErrorMessage()
        #print "Connection FAILED!"
        self.reconnectIn(60)

    def clientConnectionLost(self, connector, reason):
        print reason.getErrorMessage()
        #print "Connection LOST!"
        print "Disconnected."
        self.reconnectIn(60)
    
    def reconnectIn(self, seconds):
        global should_reconnect
        t = datetime.datetime.now()
        should_reconnect = time.mktime(t.timetuple()) + seconds

class VLC_ServerFactory(ServerFactory):
    protocol = RTP_Server

class RTP_UDP_Server0(DatagramProtocol):
    def datagramReceived(self, datagram, address):
        #print "0 => " + str(address[1])
        dataReceived(0, datagram)
        
class RTP_UDP_Server1(DatagramProtocol):
    def datagramReceived(self, datagram, address):
        #print "1 => " + str(address[1])
        dataReceived(1, datagram)
        
class RTP_UDP_Server2(DatagramProtocol):
    def datagramReceived(self, datagram, address):
        #print "2 => " + str(address[1])
        dataReceived(2, datagram)
        
class RTP_UDP_Server3(DatagramProtocol):
    def datagramReceived(self, datagram, address):
        #print "3 => " + str(address[1])
        dataReceived(3, datagram)

def dataReceived(channel, data):
    writeDebug('Receiving data from VLC...')
    writeSecretDebug('received UDP data on channel ' + str(channel))
    if packet_log:
        if channel == 0:
            global o1
            o1 += str(ord(data[3])) + ', '
        if channel == 2:
            global o2
            o2 += str(ord(data[3])) + ', '
        print "channel 0 seq: " + o1
        print "channel 2 seq: " + o2
    
    video_server_connection.writeData('$' + chr(channel) + twoByteLength(len(data)) + data)
	
    global live_sent, should_reconnect
    t = datetime.datetime.now()
    tt = time.mktime(t.timetuple())
    if tt > live_sent:
        live_sent = tt + 60
        feedback("live", "")
        #print "SENT LIVE"
    if should_reconnect != 0 and tt > should_reconnect:
        should_reconnect = 0
        #print "Attempting to reconnect..."
        
def twoByteLength(dataLength):
    v = int(math.floor(dataLength / 256))
    return chr(v) + chr(dataLength - 256 * v)

def printHelp():
    print "-----------------------------------------------------------------------"
    print "  " + user_agent + " Help - Vladislav Yazhbin <vlad@justin.tv>"
    print "-----------------------------------------------------------------------"
    print "  Please use the following command line format:\n"
    print "      jtvlc login stream_key sdp_file [-d]\n"
    print "  For example:\n"
    print "      jtvlc lin_user live_gk423_c3r4 file:///home/justin/Desktop/vlc.sdp"
    print "      jtvlc mac_user live_l01d_dlj1 /Users/Justin/Desktop/vlc.sdp"
    print "      jtvlc.exe win_user live_pj42_8fkh2 c:/users/justin/vlc.sdp\n"
    print "  -d is an optional parameter that enables debug logging to the console\n"
    print "  Please see 'readme.txt' for more information.\n"
    checkVersion()
    
def main(argv):
    #feedback("start", "Started the app")
    if len(argv) < 4 or (len(argv) > 1 and argv[1]=='--help'):
        printHelp() 
        return

    print user_agent + " By Vladislav Yazhbin <vlad@justin.tv>"
    checkVersion()
    
    global username, streamkey, sdp_location, sdp_contents, debug_log, file, uri
    username = argv[1]
    streamkey = argv[2]
    sdp_location = argv[3].replace('file://', '')
    file = '/app/live_user_' + username + '.sdp'
    uri = domain + file
    
    if len(argv) > 4 and argv[4]=="-d":
        debug_log = True
    
    if tool==Tool.VLC:
        try:
            f = open(sdp_location, 'r')
            try:
                sdp_contents = f.read().replace('\n', '\r\n').strip()
            finally:
                f.close()
        except IOError:
            error("ERROR 102:  Could not find or access file '%s'.\nSuggestions:  Have you started VLC yet?  Is it broadcasting?  Does VLC successfully create the file?  See 'readme.txt' for more information.\nAborting..." % sdp_location)
            return
        if sdp_contents == '' or sdp_contents == '(null)':
            error("ERROR 103: The sdp file is empty.  Please check your VLC streaming settings.")
            return
        global rtp_ports, rtcp_ports
        if sdp_contents.find('m=audio') > -1:
            sdp_contents = sdp_contents.replace('m=video', 'a=control:trackid=1\r\nm=video') + '\r\na=control:trackid=2'
            rtp_ports = [int(sdp_contents.partition('m=audio ')[2].partition(' RTP')[0]), int(sdp_contents.partition('m=video ')[2].partition(' RTP')[0])]
            rtcp_ports = [rtp_ports[0] + 1, rtp_ports[1] + 1]
        else:
            sdp_contents += '\r\na=control:trackid=1'
            rtp_ports = [int(sdp_contents.partition('m=video ')[2].partition(' RTP')[0])]
            rtcp_ports = [rtp_ports[0] + 1]            
        connectToVideoServer()
    else:
        sf = VLC_ServerFactory()
        reactor.listenTCP(1234, sf)
        #startListeningForRDP_UDP()
    
    reactor.run()

def startListeningForRDP_UDP():
    global rtp_ports, rtcp_ports
    reactor.listenUDP(rtp_ports[0], RTP_UDP_Server0())
    reactor.listenUDP(rtcp_ports[0], RTP_UDP_Server1())
    if len(rtp_ports) > 1: reactor.listenUDP(rtp_ports[1], RTP_UDP_Server2())
    if len(rtcp_ports) > 1: reactor.listenUDP(rtcp_ports[1], RTP_UDP_Server3())

def writeSecretDebug(msg, alternate=None):
    writeDebug(msg, True, alternate)
    
def writeDebug(msg, secret=False, alternate=None):
    if not debug_log or (not packet_log and secret):
        if alternate:
            print alternate
        return
    print msg

def connectToVideoServer():
    cf = VideoServerClientFactory()
    reactor.connectTCP(ip, port, cf)

def checkVersion():
    f = urllib.urlopen("http://vladdata.heroku.com/api/info/jtvlc.xml")
    contents = f.read()
    print "-----------------------------------------------------------------------"
    if contents.find("<version>") != -1:
        v = contents.partition("<version>")[2].partition("</version>")[0]
        if v == version:
            print "  You are using the latest version."
        else:
            print "***********************************************************************"
            print
            print "  New version of Jtvlc is available: " + v + "!"
            print "  Please visit the community wiki to download it:"
            print "  " + website
            print "-----------------------------------------------------------------------"
            return
    print "  Jtvlc homepage:  " + website
    print "-----------------------------------------------------------------------"

def error(message):
    print "  " + message
    print "-----------------------------------------------------------------------"
    feedback('error', message)

def feedback(type, message):
    u = "http://vladdata.heroku.com/api/event/jtvlc.xml?" + urllib.urlencode({'type': type, 'message': message, 'channel': username, 'key': api_key})
    if type=='error':
        urllib.urlopen(u).read()
    else:
        getPage(u).addCallback(parseResults)

def parseResults(contents):
    pass #print contents
    
if __name__ == '__main__':
    main(sys.argv)
