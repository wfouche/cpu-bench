pushd ..

rd/q/s build
rd/q/s dist

pyinstaller ..\src\cpu-bench.py

rd /q/s ..\src\__pycache__

rd/q/s build

del cpu-bench.spec

popd

