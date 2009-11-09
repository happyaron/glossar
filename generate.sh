#!/bin/sh
[ -d temp ] && rm -rf temp
mkdir temp

for i in dic/*.po; do
    export name=$(basename $i)
    export name=${name%.po}
    [ -f headers/${name}.html ] && ./po2xml.pl < $i > temp/${name}-temp.xml && cat misc/xmlhead.xml temp/${name}-temp.xml misc/xmltail.xml > temp/${name}.xml && ./divergloss/dgproc/dgproc.py html-bidict temp/${name}.xml -solang:en -stlang:zh -sfile:htmls/${name}.html -sheader:headers/${name}.html -sallinone -sstyle:igloo -sstyleopt:oterm_col_width=15em || echo "An error occured"
done

rm -rf temp

# Generate HTML glossary page and TBX file from XML
#./divergloss/dgproc/dgproc.py html-bidict gloss.xml -solang:en -stlang:zh -sfile:gloss.html -sheader:header.html -sallinone -sstyle:igloo -sstyleopt:oterm_col_width=15em
#./divergloss/dgproc/dgproc.py tbx gloss.xml -sfile:gloss.tbx
