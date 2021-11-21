# selenium-k8s-node-scaler

Custom autoscaler from Selenium Grid nodes on Kubernetes

This little Python script can scale your selenium-chrome-nodes in a Selenium Grid 4 kubernetes installation. The current [k8s full grid deployment](https://raw.githubusercontent.com/SeleniumHQ/docker-selenium/trunk/k8s-deployment-full-grid.yaml) includes deployment for Chrome, Firefox and Edge nodes, unfortunately anything you do, you always need to run at least one replica of these nodes/pods.

Furthermore these deployments do not include video recording which is pretty much a must if you are runing tests in a headless environment.

These problems are addressed with the tools in this repository.

> ⚠️ Be aware: this tool is from condultants to consultants, so you can expect rough edges, hacking left and right, unhandled race conditions, etc.


## What it does

The script runs in an infinite loop with 3 seconds sleep at the end of each cycle.

It queries Selenium sessions from the Grid, and Nodes from the k8s API in each cycle, matches these sessions with the pods.

If there are new session in the queue and there are no pods to handle them it starts new Node pod. If there is a pod without session assigned it deletes the pod. 

The started Node pods can be configured as per the `pod.yaml.j2` template. The one included in the repository contains a video recorder container where the recorded video name correlates with the Node name.

The Session information is correlated with the Node details and every Sessions information will be dumped next to the recorded video.


## Installation

1. Create a namespace called `selenium`

```fish
kubectl create ns selenium
kubectl config set-context --current --namespace selenium
```

2. Install Selenium Grid 4

```fish
kubectl apply -f https://raw.githubusercontent.com/SeleniumHQ/docker-selenium/trunk/k8s-deployment-full-grid.yaml`
```

3. Set `Replica: 0` for the node deployments

```fish
for i in chrome ff edge
  kubectl scale deployment selenium-$i-node-deployment --replicas=0
  end
```

4. Create a `StorageClass` called `selenium-fileserver-storageclass`

5. Create a `PersistentVolumeClaim` to store the test videos

```fish
kubectl apply -f https://raw.githubusercontent.com/krisek/selenium-k8s-node-scaler/trunk/k8s/fileserver-pvc.yaml
```

6. Install the tool itself

```fish
kubectl apply -f https://raw.githubusercontent.com/krisek/selenium-k8s-node-scaler/trunk/k8s/selenium-k8s-node-scaler.yaml
```

This manifest will install 

- a ServiceAccount/Role/RoleBinding that enables the scaler to interact with the cluster
- a Pod that runs the node scaler
- a Pod (and a supporting ConfigMap) that runs NGINX to provide the recorded videos

### Configuration

The tool supports several environment variables to alter parameters.

```python
# runtime arguments
poll_fequency = os.environ.get('SELENIUM_GRID_SCALER_POLL_FREQUENCY', 3) # run cycle after # seconds
node_delete_strikes = os.environ.get('SELENIUM_GRID_SCALER_NODE_DELETE_STRIKES', 20) # kill idle nodes after # cycles
selenium_videos_path = os.environ.get('SELENIUM_VIDEOS_PATH', '/tmp/videos') # videos stored at this location
selenium_namespace = os.environ.get('SELENIUM_NAMESPACE', 'selenium') # the namespace where selenium is installed
selenium_router_url = os.environ.get('SELENIUM_ROUTER_URL', 'http://selenium-router:4444')
```

## Browsing recorded videos

Simply forward the NGINX server port to your local desktop:

```fish
k port-forward pod/selenium-k8s-test-results 8000:8000
```

and point your browser to [http://localhost:8000](http://localhost:8000).


# TODO

- Proper edge and ff support.
- Better handling various race conditions
- Integration into Selenium Grid web gui ~ view past sessions and recordings

# Known issues

It can happen that sessions stuck into the Grid assigned to a Node with doesn't exist anymore. In this case you have no other choice, but deleting the various Selenium Grid components/pods until the session disappear once the deployment restarts the grid pods.

# Acknowledgements

The tool was inspired by [selenium-grid-autoscaler](https://github.com/sahajamit/selenium-grid-autoscaler).

