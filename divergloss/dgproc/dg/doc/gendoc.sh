#!/bin/sh

cd $(dirname $0)

if test x`which epydoc` = x; then
    echo "Epydoc not found."
    exit 1
fi

# Proper module path for epydoc to follow.
export PYTHONPATH=../../:$PYTHONPATH

rm -rf doc/*

epydoc dg \
       -o html -v \
       --no-sourcecode --no-frames --no-private --exclude=external

# Kill generation timestamps, to not have diffs just due to it.
  find html -iname \*.html \
| xargs perl -pi -e 's/(Generated\b.*?) *on\b.*?(<|$)/$1$2/'

