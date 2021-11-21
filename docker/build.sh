#!bash
BUILDDIR=/tmp/selenium-k8s-node-scaler
rm -rf $BUILDDIR
mkdir -p $BUILDDIR
cp ../selenium-k8s-node-scaler.py $BUILDDIR
cp ../requirements.txt $BUILDDIR
cp ../pod.yaml.j2 $BUILDDIR
cp Dockerfile $BUILDDIR

cd $BUILDDIR

podman build -t selenium-k8s-node-scaler .
podman tag localhost/selenium-k8s-node-scaler:latest docker.io/krisek11/selenium-k8s-node-scaler:latest
podman push krisek11/selenium-k8s-node-scaler:latest