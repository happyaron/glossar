#!/usr/bin/perl -w
use strict;

my %idcounts;
my @comment;
my $zh;
my $en;
my $status;
my $id;

while (<>) {
    chomp;
    unless (m/^".*$/) {
        if (m/^#\s*(.*)$/) {
            push @comment, $1;
        }
        elsif (m/^msgid\s*\"(.+)\"$/) {
            $en = $1;
        }
        elsif (m/^msgstr\s*\"(.+)\"$/) {
            $zh = $1;
            $status = 1;
        }
    }
    if ($status) {
        $en =~ s/&/and/;
        $id = $en;
        $id =~ tr/[A-Z ]/[a-z_]/;
        $id =~ s/\W//g;
        if (exists $idcounts{$id}) {
            $idcounts{$id} ++;
            $id = $id.$idcounts{$id};
        }
        else {
            $idcounts{$id} = 1;
        }

        print "    <concept id=\"$id\">\n";

        if (@comment == 1) {
            print "      <desc>$comment[0]</desc>\n";
        }
        elsif (@comment > 1) {
            print "      <ldesc>\n";
            foreach (@comment) {
                print "        <para>$_</para>\n";
            }
            print "      </ldesc>\n";
        }

        print "      <term lang=\"en\">$en</term>\n";
        print "      <term>$zh</term>\n";
        print "    </concept>\n\n";

        {
        $status = 0;
        undef @comment;
        undef $zh;
        undef $en;
        }
    }
}
