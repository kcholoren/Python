#!/usr/bin/env python
# ------------------------------------------------------- #
# BibTeX reducer                                          #
# Miminize a BibTeX file according the actual citations   #
# ------------------------------------------------------- #
# usage: reducer.py -b bibtex.bib -a paper.aux ---------- #
# ------------------------------------------------------- #
# Kcho                                                    #
# UNS - DCIC 2013-2015                                    #
# http://ir.cs.uns.edu.ar -~- mailto cml at cs.uns.edu.ar #
# ------------------------------------------------------- #

import sys
from optparse import OptionParser
# read parameters
optis = OptionParser()

optis.add_option("-b", "--bibtex", dest="bib",
                 help="File containing the bibtex original data", metavar="FILE")
optis.add_option("-a", "--aux", dest="aux",
                 help="File containing the auxiliary file", metavar="FILE")


(options, args) = optis.parse_args()


if (not options.bib):
  print "There is no BibTeX file (-b option)"
  optis.print_help()
  sys.exit(-1)

if (not options.aux):
  print "There is no Auxiliary file (-a option)"
  optis.print_help()
  sys.exit(-1)

fs = open(options.aux, 'r')
citas = set()
while True:
  line = fs.readline()
  if not line:
    break
  if 0==line.find("\citation"):
    cita=line.replace("\citation{","").replace("}","").strip().lower()
    citas.add(cita)

fs.close()

if len(citas)>0:
  import bibtexparser
  
  with open(options.bib, 'r') as bibtex_file:
    bibtex_str = bibtex_file.read()
  bib_database = bibtexparser.loads(bibtex_str)
  
  with open(options.bib+'reduced.bib', 'w') as ofs:
    for entry in bib_database.entries:
      bibkey = entry['id'].lower()
      if bibkey in citas:
	reconstruct_bib = "@"+entry['type']+"{"+entry['id']+",\n"
	for y in [k for k in entry if (k!='id')&(k!='type')]:
	  reconstruct_bib += "\t"+y+" = {"+str(entry[y])+"},\n"
	reconstruct_bib += "}\n\n"
	ofs.write(reconstruct_bib)
	citas.remove(bibkey)
    if (len(citas)>0):
      print len(citas),"keys not found!!"
else:
  print "No cites found in aux file"
