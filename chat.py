#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, argparse, time, subprocess, logging, os, redis, threading, json
from bigbluebutton_api_python import BigBlueButton
from bigbluebutton_api_python import util as bbbUtil 
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

browser = None
selenium_timeout = 30
connect_timeout = 5

# Configure logging to console and file
log_level = os.environ.get('LOGLEVEL', 'INFO')
logging.basicConfig(level=log_level)
LOG_DIR = os.environ.get('BBB_LOG_DIR', os.path.join(os.getcwd(), 'logs'))
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except PermissionError:
    LOG_DIR = '/tmp/logs'
    os.makedirs(LOG_DIR, exist_ok=True)
_fh = logging.FileHandler(os.path.join(LOG_DIR, 'chat-app.log'))
_fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logging.getLogger().addHandler(_fh)

parser = argparse.ArgumentParser()
parser.add_argument("-s","--server", help="Big Blue Button Server URL")
parser.add_argument("-p","--secret", help="Big Blue Button Secret")
parser.add_argument("-i","--id", help="Big Blue Button Meeting ID")
parser.add_argument("-S","--startMeeting", help="start the meeting if not running",action="store_true")
parser.add_argument("-A","--attendeePassword", help="attendee password (required to create meetings)")
parser.add_argument("-M","--moderatorPassword", help="moderator password (required to create a meeting)")
parser.add_argument("-T","--meetingTitle", help="meeting title (required to create a meeting)")
parser.add_argument("-u","--user", help="Name to join the meeting",default="Live")
parser.add_argument("-r","--redis", help="Redis hostname",default="redis")
parser.add_argument("-c","--channel", help="Redis channel",default="chat")
parser.add_argument("--browser", help="Browser to use: chrome, firefox, or edge", default=os.environ.get('BROWSER', 'chrome'))
parser.add_argument(
   '--browser-disable-dev-shm-usage', action='store_true', default=False,
   help='do not use /dev/shm',
)
args = parser.parse_args()

bbb = BigBlueButton(args.server,args.secret)
bbbUB = bbbUtil.UrlBuilder(args.server,args.secret)

def set_up():
    global browser
    browser_choice = (args.browser or 'chrome').lower()
    if browser_choice == 'firefox':
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        options = FirefoxOptions()
        options.set_preference('intl.accept_languages', 'en-US,en')
        options.set_preference('security.certerrors.permanentOverride', True)
        options.set_preference('security.enterprise_roots.enabled', True)
        options.set_preference('security.mixed_content.block_active_content', False)
        # Autoplay and media permissions for chat window as well
        options.set_preference('media.autoplay.default', 0)
        options.set_preference('media.autoplay.blocking_policy', 0)
        options.set_preference('media.autoplay.enabled', True)
        options.set_preference('media.navigator.permission.disabled', True)
        options.set_preference('media.navigator.streams.fake', True)
        options.set_preference('permissions.default.microphone', 1)  # 1=allow
        options.set_preference('permissions.default.camera', 1)      # 1=allow
        options.set_preference('media.peerconnection.enabled', True)
        options.set_capability('acceptInsecureCerts', True)
        options.add_argument('--kiosk')
        options.add_argument('--start-fullscreen')
    elif browser_choice == 'edge':
        from selenium.webdriver.edge.options import Options as EdgeOptions
        options = EdgeOptions()
        options.use_chromium = True
        options.add_argument('--disable-infobars')
        options.add_argument('--no-sandbox')
        options.add_argument('--kiosk')
        options.add_argument('--start-fullscreen')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--allow-running-insecure-content')
        options.set_capability('acceptInsecureCerts', True)
        options.add_argument('--window-size=1280,720')
        options.add_argument('--window-position=0,0')
        options.add_argument('--incognito')
        options.binary_location = '/usr/bin/microsoft-edge'
    else:
        options = Options()
        options.add_argument('--disable-infobars')
        options.add_argument('--no-sandbox')
        options.add_argument('--kiosk')
        options.add_argument('--window-size=1280,720')  # we do not need a big window for the chat
        options.add_argument('--window-position=0,0')
        options.add_experimental_option("excludeSwitches", ['enable-automation'])
        options.add_argument('--incognito')
        options.add_argument('--start-fullscreen')
        options.add_argument('--use-fake-ui-for-media-stream')
        # Enable Chrome logging for console and performance (network/websocket) events
        options.add_argument('--enable-logging')
        options.add_argument('--v=1')
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
        options.set_capability('goog:chromeOptions', {
            'perfLoggingPrefs': {
                'enableNetwork': True,
                'enablePage': True,
            }
        })
        # Allow insecure certs if BBB uses self-signed or mismatched cert to avoid blocked wss
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--allow-running-insecure-content')
        options.set_capability('acceptInsecureCerts', True)
        options.add_argument('--remote-allow-origins=*')
    if args.browser_disable_dev_shm_usage:
        options.add_argument('--disable-dev-shm-usage')
    else:
        dev_shm_size = int(subprocess.run('df /dev/shm/ --block-size=1M --output=size | tail -n 1', shell=True, stdout=subprocess.PIPE).stdout or '0')
        required_dev_shm_size = 500  # in MB, 1024MB is recommended
        if dev_shm_size < required_dev_shm_size:
            logging.error(
                'The size of /dev/shm/ is %sMB (minimum recommended is %sMB), '
                'consider increasing the size of /dev/shm/ (shm-size docker parameter) or disabling /dev/shm usage '
                '(see --browser-disable-dev-shm-usage or BROWSER_DISABLE_DEV_SHM_USAGE env variable).',
                dev_shm_size, required_dev_shm_size
            )
            sys.exit(2)

    logging.info('Starting browser to chat!! (%s)', browser_choice)

    if browser_choice == 'firefox':
        from selenium.webdriver.firefox.service import Service as FirefoxService
        service = FirefoxService(executable_path='/usr/local/bin/geckodriver', log_output=os.path.join(LOG_DIR, 'geckodriver-chat.log'))
        browser = webdriver.Firefox(service=service, options=options)
    elif browser_choice == 'edge':
        from selenium.webdriver.edge.service import Service as EdgeService
        service = EdgeService(executable_path='/usr/local/bin/msedgedriver', log_output=os.path.join(LOG_DIR, 'msedgedriver-chat.log'))
        browser = webdriver.Edge(service=service, options=options)
    else:
        # Use Chrome for Testing binary and matching chromedriver
        options.binary_location = '/opt/chrome-linux64/chrome'
        service = Service(executable_path='./chromedriver', log_output=os.path.join(LOG_DIR, 'chromedriver-chat.log'))
        browser = webdriver.Chrome(service=service, options=options)
    start_browser_log_capture(browser, LOG_DIR)

def bbb_browser():
    global browser

    logging.info('Open BBB for chat!!')
    if args.startMeeting is True:
        try:
            logging.info("create_meeting...")
            create_meeting()
        except exception.bbbexception.BBBException as ERR:
            logging.info(ERR)

    join_url = get_join_url()
    logging.info(join_url)
    browser.get(join_url)

    time.sleep(6)

    element = EC.invisibility_of_element((By.CSS_SELECTOR, '.ReactModal__Overlay'))
    WebDriverWait(browser, selenium_timeout).until(element)
    browser.find_element_by_id('message-input').send_keys("Viewers of the live stream can now send messages to this meeting")
    browser.find_elements_by_css_selector('[aria-label="Send message"]')[0].click()

    redis_r = redis.Redis(host=args.redis,charset="utf-8", decode_responses=True)
    redis_s = redis_r.pubsub()
    redis_s.psubscribe(**{args.channel:chat_handler})
    thread = redis_s.run_in_thread(sleep_time=0.001)

def chat_handler(message):
    global browser
    browser.find_element_by_id('message-input').send_keys(message['data'])
    browser.find_elements_by_css_selector('[aria-label="Send message"]')[0].click()
    logging.info(message['data'])

def create_meeting():
    create_params = {}
    if args.moderatorPassword:
        create_params['moderatorPW'] = args.moderatorPassword
    if args.attendeePassword:
        create_params['attendeePW'] = args.attendeePassword
    if args.meetingTitle:
        create_params['name'] = args.meetingTitle
    return bbb.create_meeting(args.id, params=create_params)

def get_join_url():
    minfo = bbb.get_meeting_info(args.id)
    pwd = minfo.get_meetinginfo().get_attendeepw()
    joinParams = {}
    joinParams['meetingID'] = args.id
    joinParams['fullName'] = args.user
    joinParams['password'] = pwd
    joinParams['userdata-bbb_auto_join_audio'] = "false"
    joinParams['userdata-bbb_enable_video'] = 'false' 
    joinParams['userdata-bbb_listen_only_mode'] = "true" 
    joinParams['userdata-bbb_force_listen_only'] = "true" 
    joinParams['userdata-bbb_skip_check_audio'] = 'true' 
    joinParams['joinViaHtml5'] = 'true'
    return bbbUB.buildUrl("join", params=joinParams) 


def chat():
    while True:
        time.sleep(60)

def start_browser_log_capture(driver, log_dir):
    """Continuously capture browser console and performance logs to files."""
    console_path = os.path.join(log_dir, 'chat-browser-console.log')
    perf_path = os.path.join(log_dir, 'chat-browser-performance.jsonl')

    def _writer_loop():
        while True:
            try:
                # Console logs
                try:
                    entries = driver.get_log('browser')
                    if entries:
                        with open(console_path, 'a', encoding='utf-8') as f:
                            for e in entries:
                                ts = e.get('timestamp')
                                level = e.get('level')
                                msg = e.get('message')
                                f.write(f"{ts} {level} {msg}\n")
                except Exception as e:
                    logging.debug('Error reading chat browser console logs: %s', e)

                # Performance logs (network/websocket)
                try:
                    entries = driver.get_log('performance')
                    if entries:
                        with open(perf_path, 'a', encoding='utf-8') as f:
                            for e in entries:
                                try:
                                    f.write(e['message'] + '\n')
                                except Exception:
                                    f.write(json.dumps(e) + '\n')
                except Exception as e:
                    logging.debug('Error reading chat performance logs: %s', e)
            except Exception as e:
                logging.debug('Error in chat log capture loop: %s', e)
            time.sleep(2)

    t = threading.Thread(target=_writer_loop, daemon=True)
    t.start()


while bbb.is_meeting_running(args.id).is_meeting_running() != True:
    time.sleep(connect_timeout)
set_up()
bbb_browser()
chat()
browser.quit()

