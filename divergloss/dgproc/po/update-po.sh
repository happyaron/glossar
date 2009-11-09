#!/bin/sh

wdir=`pwd`
cdir=`dirname $0`
potbase=dgproc

mode=all
if test -n "$1"; then
    mode=$1
fi

if test $mode = all || test $mode = extract; then
    echo ">>> Extracting POT..."
    cd $cdir/..
    srcfiles=`find -iname \*.py | sort`
    potfile=po/$potbase.pot
    xgettext --no-wrap \
        -k_:1 -kp_:1c,2 -kn_:1,2 -knp_:1c,2,3 \
        -o $potfile $srcfiles
    cd $wdir
fi

if test $mode = all || test $mode = merge; then
    echo ">>> Merging POs..."
    potfile=$cdir/$potbase.pot
    pofiles=`echo $cdir/*.po`
    for pofile in $pofiles; do
        echo -n "$pofile  "
        msgmerge -U --backup=none --no-wrap --previous $pofile $potfile
    done
fi

# Generate sr@latin PO if sr present.
if test -f $cdir/sr.po; then
    recode-sr-latin <$cdir/sr.po >$cdir/sr@latin.po
fi

if test $mode = all || test $mode = compile; then
    echo ">>> Compiling MOs..."
    modir=$cdir/../mo
    # Remove old MO dir if in pristine state, otherwise warn and exit.
    if [ -d $modir ]; then
        nonmofiles=`find $modir -type f | egrep -v '.*\.mo$'`
        if [ -n "$nonmofiles" ]; then
            echo "$nonmofiles"
            echo ">>> $modir contains non-MO files."
            echo ">>> Move them or delete them, then rerun the script."
            exit 1
        fi
        rm -rf $modir
    elif [ -e $modir ]; then
        echo ">>> $modir not a directory."
        echo ">>> Move it or delete it, then rerun the script."
        exit 1
    fi

    pofiles=`echo $cdir/*.po`
    for pofile in $pofiles; do
        echo -n "$pofile  "
        pobase=`basename $pofile`
        lang=${pobase/.po/}
        mosubdir=$modir/$lang/LC_MESSAGES
        mkdir -p $mosubdir
        mofile=$mosubdir/$potbase.mo
        msgfmt -c --statistics $pofile -o $mofile
    done
fi
