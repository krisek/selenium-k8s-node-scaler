#!python3

import requests
from kubernetes import client, config, utils
import yaml
import os
import json
import time
import logging
from jinja2 import Template
from tempfile import mkstemp
from datetime import datetime as dt
import pathlib
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)




# runtime arguments
poll_fequency = os.environ.get('SELENIUM_GRID_SCALER_POLL_FREQUENCY', 3) # run cycle after # seconds
node_delete_strikes = os.environ.get('SELENIUM_GRID_SCALER_NODE_DELETE_STRIKES', 20) # kill idle nodes after # cycles
selenium_videos_path = os.environ.get('SELENIUM_VIDEOS_PATH', '/tmp/videos') # videos stored at this location
selenium_namespace = os.environ.get('SELENIUM_NAMESPACE', 'selenium') # the namespace where selenium is installed
selenium_router_url = os.environ.get('SELENIUM_ROUTER_URL', 'http://selenium-router:4444')

# read and init selenium node pod template 
with open('pod.yaml.j2') as file:
    tpl = file.read()

tm = Template(tpl, trim_blocks=True, lstrip_blocks=True)

def generateKubeConfig():
  tpl = '''apiVersion: v1
clusters:
- cluster:
    insecure-skip-tls-verify: true
    server: https://kubernetes.default.svc
  name: default
contexts:
- context:
    cluster: default
    namespace: selenium
    user: system:serviceaccount:selenium:auto-scale-robot
  name: default
current-context: "default"
kind: Config
preferences: {}
users:
- name: system:serviceaccount:selenium:auto-scale-robot
  user:
    token: /run/secrets/kubernetes.io/serviceaccount/token
'''
  with open('/run/secrets/kubernetes.io/serviceaccount/token') as file:
    token = file.read()
  config = yaml.load(tpl, Loader=yaml.FullLoader)
  config['users'][0]['user']['token'] = token
  return config

# init k8s
if os.path.isfile('/run/secrets/kubernetes.io/serviceaccount/token'):
   config.load_kube_config_from_dict(generateKubeConfig())
else:
  config.load_kube_config()

k8sclient = client.CoreV1Api()
k8sapiclient = client.ApiClient()

# variables for the whole run
started_pods = {}
k8s_pods = {}
new_sessions = 0
new_sessions_old = 0
global_sessions = []

# our selenium query
data = '{"operationName":"GetSessions","variables":{},"query":"query GetSessions {\n  sessionsInfo {\n    sessions {\n      id\n      capabilities\n      startTime\n      uri\n      nodeId\n      nodeUri\n      sessionDurationMillis\n      slot {\n        id\n        stereotype\n        lastStarted\n        __typename\n      }\n      __typename\n    }\n    sessionQueueRequests\n    __typename\n  }\n}\n"}'


# in every cycle we retrieve
# - selenium session info (contains existing and new sessions)
# - kubernetes pods with label/type selenium-node
# with this information
# - we update a dictionary that holds pods info across cycles
# - we create a dictionary that holds pods info in the cycle
# - we check selenium sessions, and update pods info with session info (session nodeUri ~ pod
# - once a new session is found it's info is written out to a directory secific for the matching pod
# - if we have new sessions since last cycle and no idleing nodes we schedule new pod
# - we check if all pods in this cycle have a session (if not give them a strike)
# - we delete pods that have too many strikes

# possible race conditions
# - session is not picked up by node before reaching strike limit 
#     (pod will be deleted, but still there might be a session attached - too late)


while True:
  
  try:
    r = requests.post(selenium_router_url + '/graphql', verify=False, data=data)
    k = k8sclient.list_namespaced_pod(namespace=selenium_namespace, watch=False, label_selector='type=selenium-node')

    sessions_info = json.loads(r.text)
    logging.debug(sessions_info)
    sessions = sessions_info.get('data',{}).get('sessionsInfo', {}).get('sessions',[])

    # try to mach pods with session
    active_pods = {}
    
    for pod in k.items:    
      logging.info("test pod on {} {}".format(pod.metadata.name, pod.status.pod_ip))
      if pod.status.pod_ip is not None:
        if pod.status.pod_ip not in k8s_pods:
          k8s_pods[pod.status.pod_ip] = {'name': pod.metadata.name, 'session_id': pod.metadata.labels['scalerSessionId'], 'strike':0}
        active_pods[pod.status.pod_ip] = {'name': pod.metadata.name, 'session_id': pod.metadata.labels['scalerSessionId'] }

    for session in sessions:
      session['ip'] = session['nodeUri'].replace('http://','').replace(':5555','')
      logging.info("session id: {} running on: {}".format(session['id'], session['ip']))

      if session['ip'] in k8s_pods and session['ip'] in active_pods:
        k8s_pods[session['ip']]['session'] = session
        k8s_pods[session['ip']]['strike'] = 0
        active_pods[session['ip']]['session'] = session
      else:
        logging.error("pod on {} lost".format(session['ip']))
        
      if session['id'] not in global_sessions:
        # save information about the session (correlated with videos)
        target_file = "{}/{}/{}".format(selenium_videos_path, k8s_pods[session['ip']]['session_id'],session['id'])
        pathlib.Path(os.path.dirname(target_file)).mkdir(parents=True, exist_ok=True)
        with open(target_file, "w") as session_file:
          session_file.write(json.dumps(session, indent=4, sort_keys=True)) 
        global_sessions.append(session['id'])
        os.system("tree -H /videos {} > {}/index.html".format(selenium_videos_path, selenium_videos_path))

    # schedule new sessions if neeeded
    new_sessions_old = new_sessions
    new_sessions = len(sessions_info.get('data',{}).get('sessionsInfo', {}).get('sessionQueueRequests',[]))
    new_sessions_diff = new_sessions - new_sessions_old  
    
    logging.info("grid sessions: {} new sessions: {} active testing pods: {} ({}) ".format(len(sessions), new_sessions, len(active_pods.keys()), "/".join(active_pods.keys())))  
    
    if new_sessions_diff > 0 and len(active_pods.keys()) < len(sessions) + new_sessions:
      # start new pod
      fd, path = mkstemp()
      session_id = "{}-{}".format(dt.now().strftime('%Y%m%d%H%M'),os.path.basename(path).replace('tmp', '').replace('_',''))
      pod_data = {
        'session_id': session_id,
        'browser': 'chrome'
      }
      logging.debug(tm.render(pod_data))
      utils.create_from_yaml(k8sapiclient, yaml_objects=[yaml.load(tm.render(pod_data),  Loader=yaml.FullLoader)])
      logging.info("new pod started {}".format(session_id))

    # find pods without session and strike them
    for ip in active_pods.keys():
      if 'session' not in active_pods[ip]:
        k8s_pods[ip]['strike'] += 1
        logging.info("no session for pod {} strike: {}/{}".format(active_pods[ip]['name'], k8s_pods[ip]['strike'], node_delete_strikes))
      else:
        logging.info("session for pod {} {}".format(active_pods[ip]['name'], k8s_pods[ip]['session']['id']))

    # kill pods without session for node_delete_strikes cycles
    pods_to_delete = []
    for ip in k8s_pods.keys():
      if k8s_pods[ip]['strike'] >= node_delete_strikes and new_sessions == 0:
        pods_to_delete.append(ip)
        
    for ip in pods_to_delete:
      try:
        k8sclient.delete_namespaced_pod(k8s_pods[ip]['name'], selenium_namespace)
        logging.info("deleted pod {}".format(k8s_pods[ip]['name']))
      except Exception as re:
        logging.error("error (delete) {} {}".format(type(re).__name__, re))
      finally:
        del k8s_pods[ip]
      
  except Exception as e:
    logging.error("error {} {}".format(type(e).__name__, e))
    new_sessions = 0

  time.sleep(poll_fequency)