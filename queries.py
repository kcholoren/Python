# ------------------------------------------------------- #
#             CXL Concept Maps query creator              #
# ------------------------------------------------------- #
#                          Kcho                           #
#                     UNS - DCIC 2013                     #
# http://ir.cs.uns.edu.ar -~- mailto cml at cs.uns.edu.ar #
# ------------------------------------------------------- #
from optparse import OptionParser
from BeautifulSoup import BeautifulSoup
import sys
import numpy as Numeric
from pysparse import spmatrix
from igraph import *
# ---------------------------------------------
def find_id(c,h):
  i = 0
  for e in c:
    if (e['id']==h):
      return i
    i = i + 1
  return None
# ---------------------------------------------
def add_vertex_with_attrs(graph, attrs):
    n = graph.vcount()
    graph.add_vertices(1)
    for key, value in attrs.iteritems():
        graph.vs[n][key] = value
# ---------------------------------------------
def clean_stop_words(l):
  ret=[]
  for a in l:
    label = a['label'].encode('ascii').lower()
    l_new = ''
    for o in label.split(' '):
      if (not o in stop_words):
	l_new = l_new + ' ' + o
    l_new = l_new.strip()
    if (len(l_new)>0):
      a['label']=l_new
      ret.append(a)
  return ret
# ---------------------------------------------
# remove repeated words in two strings
#
# Kcho - 2013
# ---------------------------------------------
def remove_repeated(a,b):
  if (type(a) is not str):
    if (type(b) is not str): # both variables are not string, nothing to do
      return None
    else: # just 'b' is a string
      return b
  else: # 'a' is a string
    if (type(b) is not str): # just 'a' is a string
      return a
    else: # both variable are string, do the job
      c_arr=a.split()
      b_arr=b.split()
      for i in b_arr:
	if i not in c_arr:c_arr.append(i)
      
      return ' '.join([str(x) for x in c_arr])
# ---------------------------------------------  

# read parameters 
optis = OptionParser()
optis.add_option("-f", "--file", dest="filename",
                  help="file to parse", metavar="FILE")

(options, args) = optis.parse_args()
# open file
try:
  f = open(options.filename, 'r')
except IOError:
  print options.filename, 'not found'
  sys.exit(-1)
else:  
  # read file
  data1 = f.read()
  # delete newlines and other things
  data = data1.replace('\n','').replace('\r',' ').replace(',',' ').replace('- ','').replace(' -','-').replace(' +','+').replace('\'s','').replace('(',' ').replace(')',' ').replace('~',' ').replace('&quot;','').replace('&amp;', ' ').replace('&nbsp;', ' ').replace('&#xa;',' ').replace('&','').replace('  ', ' ')
  # parse 
  soup = BeautifulSoup(data, convertEntities=BeautifulSoup.HTML_ENTITIES)
  # find all the table rows
  concepts = soup.findAll('concept')
  linkingphrases = soup.findAll('linking-phrase')
  connections = soup.findAll('connection')

  stop_words=['by','an','a', 'from','for','be','with','of','at','and','in','the','or','to']

  grafo = Graph(0, directed=True) # zero vertices, default is one
  grafo_solo_conceptos = Graph(0, directed=True)
  grafo_LCL = Graph(0, directed=True)

  #
  concepts	=	clean_stop_words(concepts)
  
  # add concept to all graphs
  for co in concepts:
    add_vertex_with_attrs( grafo, {'label':co['label'].encode('ascii').lower(), 'color':'blue'})
    add_vertex_with_attrs( grafo_solo_conceptos, {'label':co['label'].encode('ascii').lower(), 'color':'blue'})
    add_vertex_with_attrs( grafo_LCL, {'label':co['label'].encode('ascii').lower(), 'color':'blue'})

  # remove stop words in linking phrases (LFs)
  linkingphrases	=	clean_stop_words(linkingphrases)

  # add links between concepts and the remaining LFs
  for co in linkingphrases:
    label = co['label'].encode('ascii').lower()
    add_vertex_with_attrs( grafo, {'label':label, 'color':'red'})
    add_vertex_with_attrs( grafo_LCL, {'label':label, 'color':'red'})
    
  for c in connections:
      from_id=find_id(concepts, c['from-id'])
      to_id=find_id(concepts, c['to-id'])
      if (from_id==None): # from is LinkingF
	from_id_aux=find_id(linkingphrases, c['from-id'])
	if (from_id_aux!=None): # from was not erased because it isnt a stopword
	  from_id=from_id_aux+len(concepts)
	  grafo_LCL.add_edges([(to_id,from_id)]) # add a link in inverse way
	else:
	  continue
      if (to_id==None): # to is LF
	to_id_aux=find_id(linkingphrases, c['to-id'])
	if (to_id_aux!=None):
	  to_id=to_id_aux+len(concepts)
	else: # to was suppressed
	  continue
      grafo.add_edges([(from_id,to_id)])

  # create links in the graph with only concepts. ie. replace C1->L->C2 with C1->C2
  # it is usefull to create CCC queries
  for x in grafo.vs():
    if (x['color']=='blue'):
      for suc in grafo.successors(x.index):
	grafo_LCL.add_edges([(x.index, suc)])
	for suc2 in grafo.successors(suc):
	  grafo_solo_conceptos.add_edges([(x.index,suc2)])

  # CCC queries
  ccc_qs=[]
  for x in grafo_solo_conceptos.vs():
    l1 = x['label']
    past = []
    for suc in grafo_solo_conceptos.successors(x.index):
      l2 = grafo_solo_conceptos.vs()[suc]['label']
      for suc2 in grafo_solo_conceptos.successors(suc):
	l3 = grafo_solo_conceptos.vs()[suc2]['label']
	ccc_qs.append(remove_repeated(remove_repeated(l1,l2),l3))
      if (len(past)>0):
	for p in past:
	  ccc_qs.append(remove_repeated(remove_repeated(l1,l2),p))
      past.append(l2)

  # LCL queries
  lcl_qs=[]
  lll_qs=[]
  for x in grafo_LCL.vs():
    sucs=grafo_LCL.successors(x.index)
    l = len(sucs)
    if (l>1):
      for i in range(l):
	l1=grafo_LCL.vs()[sucs[i]]['label']
	for j in range(l):
	  l2=grafo_LCL.vs()[sucs[j]]['label']
	  if (j>i):
	    # remove repeated terms and create a string
	    aux=remove_repeated(remove_repeated(x['label'],l1),l2)
	    aux_arr=aux.split()
	    if (len(aux_arr)>2):
	      aux_arr.sort()
	      aux_str=' '.join([str(m) for m in aux_arr])
	      if (aux_str not in lcl_qs):
		lcl_qs.append(aux_str)
      # LLL queries
      if (l>2):
	for i in range(l):	
	  l1=grafo_LCL.vs()[sucs[i]]['label']
	  for j in range(l):
	    if (i>=j): continue # not process the same combination twice
	    l2=grafo_LCL.vs()[sucs[j]]['label']
	    for k in range(l):
	      if (k>=j):continue # not process the same combination twice
	      if (i>=k):continue # not process the same combination twice
	      l3=grafo_LCL.vs()[sucs[k]]['label']
	      # remove repeated terms and create a string
	      aux=remove_repeated(remove_repeated(l1,l2),l3)
	      aux_arr=aux.split()
	      # test if length enough
	      if (len(aux_arr)>2):
		# test if it is not already inserted
		#
		# sort alphabetically and rejoin
		aux_arr.sort()
		aux_str=(' '.join([str(x) for x in aux_arr]))
		if (aux_str not in lll_qs):
		  lll_qs.append(aux_str)

  ##for a in delete_repeated(lll2_qs):
  #for a in ccc_qs:
    #print a

  #sys.exit(0)

  f_ccc=open('ccc_'+options.filename+'.txt','w')
  f_lcl=open('lcl_'+options.filename+'.txt','w')
  f_lll=open('lll_'+options.filename+'.txt','w')

  # print to a file with array to string space-separated conversion
  for a in ccc_qs:
    print>>f_ccc, a
  f_ccc.close()

  for a in lcl_qs:
    print>>f_lcl, a
  f_lcl.close()

  for a in lll_qs:
    print>>f_lll, a
  f_lll.close()


  #fig=Plot()
  #fig.add(grafo, layout="fr")
  #fig.show()
