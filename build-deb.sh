mkdir -p usr/bin
gcc Jan-amoled.c -o usr/bin/Jan-amoled
dpkg-deb --build ./ jan-amoled.deb
# Clean up artifacts (Which usr/bin technically is)
rm -rf usr/bin
