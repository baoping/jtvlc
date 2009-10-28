# app specific
version = '0.41'
user_agent = 'Justin.tv Jtvlc ' + version
api_key = 'jla8h4Dei14Tr2'
website = 'http://community.justin.tv/mediawiki/index.php/Vlc'

# user specific
username = ''
streamkey = ''
sdp_location = ''

# justin.tv specific
realm = 'Justin.tv'
password = 'jtv'
ip = 'live.justin.tv'
port = 1935
domain = 'rtsp://%s:%d' % (ip, port)
file = ''
uri = ''

packet_log = False
debug_log = False
video_server_connection = None
sdp_contents = None
rtp_ports = []
rtcp_ports = []
o1 = ''
o2 = ''
live_sent = 0
should_reconnect = 0
