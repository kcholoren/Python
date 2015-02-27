__author__ = 'kcho'


# ------------------------------------------------------- #
# CXL Concept Maps query creator                          #
# ------------------------------------------------------- #
# usage: python queries.py -f file.cxl ------------------ #
# ------------------------------------------------------- #
# Kcho                                                    #
# UNS - DCIC 2013-2015                                    #
# http://ir.cs.uns.edu.ar -~- mailto cml at cs.uns.edu.ar #
# ------------------------------------------------------- #
from optparse import OptionParser
from BeautifulSoup import BeautifulSoup
# import sys
# import numpy as Numeric
# from pysparse import spmatrix
from igraph import *
# ---------------------------------------------


def find_id(concept, h):
    """

    :type concept: Collection.iterable
    """
    id_found = 0
    for e in concept:
        if e['id'] == h:
            return id_found
        id_found += 1
    return None


# ---------------------------------------------
def add_vertex_with_attrs(graph, attrs):
    """

    :param graph:
    :param attrs:
    """
    n = graph.vcount()
    graph.add_vertices(1)
    for key, value in attrs.iteritems():
        graph.vs[n][key] = value


# ---------------------------------------------
def clean_stop_words(soup_list):
    ret = []
    for element in soup_list:
        element_label = element['label'].encode('ascii').lower()
        l_new = ''
        for o in element_label.split(' '):
            if o not in stop_words:
                l_new = l_new + ' ' + o
        l_new = l_new.strip()
        if len(l_new) > 0:
            element['label'] = l_new
            ret.append(element)
    return ret


# ---------------------------------------------


def remove_repeated(string1, string2):
    # remove repeated words in two strings
    """

    :param string1:
    :param string2:
    :return:
    """
    if type(string1) is not str:
        if type(string2) is not str:  # both variables are not string, nothing to do
            return None
        else:  # just 'string2' is a string
            return string2
    else:  # 'string1' is a string
        if type(string2) is not str:  # just 'string1' is a string
            return string1
        else:  # both variable are string, do the job
            c_arr = string1.split()
            b_arr = string2.split()
            for element_of_b in b_arr:
                if element_of_b not in c_arr:
                    c_arr.append(element_of_b)

            return ' '.join([str(str_x) for str_x in c_arr])

# ---------------------------------------------


def sort_and_add_non_repeated(list_of_queries, str_part1, str_part2):
    # remove repeated terms and create a string
    """

    :rtype : list
    """
    str_1_non_rep = remove_repeated(str_part1, str_part2)
    str_1_non_rep_arr = str_1_non_rep.split()
    if len(str_1_non_rep_arr) > 2:
        str_1_non_rep_arr.sort()
        str_1_non_rep = ' '.join([str(elem) for elem in str_1_non_rep_arr])
        if str_1_non_rep not in list_of_queries:
            list_of_queries.append(str_1_non_rep)

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
    data = data1.replace('\n', '').replace('\r', ' ').replace(',', ' ').replace('- ', '').replace(' -', '-').replace(
        ' +', '+').replace('\'s', '').replace('(', ' ').replace(')', ' ').replace('~', ' ').replace('&quot;',
                                                                                                    '').replace('&amp;',
                                                                                                                ' ').replace(
        '&nbsp;', ' ').replace('&#xa;', ' ').replace('&', '').replace('  ', ' ')
    # parse
    soup = BeautifulSoup(data, convertEntities=BeautifulSoup.HTML_ENTITIES)
    # find all the table rows
    Concepts = soup.findAll('concept')
    LinkingPhrases = soup.findAll('linking-phrase')
    connections = soup.findAll('connection')

    stop_words = ['by', 'an', 'a', 'from', 'for', 'be', 'with', 'of', 'at', 'and', 'in', 'the', 'or', 'to']

    Full_Graph = Graph(0, directed=True)  # zero vertices, default is one
    Only_Concepts_Graph = Graph(0, directed=False)
    LCL_Aux_Graph = Graph(0, directed=True)
    CLC_Aux_Graph = Graph(0, directed=True)

    #
    Concepts = clean_stop_words(Concepts)

    # add concept to all graphs
    # concepts will be blue colored
    for co in Concepts:
        label = co['label'].encode('ascii').lower()
        add_vertex_with_attrs(Full_Graph, {'label': label, 'color': 'blue'})
        add_vertex_with_attrs(Only_Concepts_Graph, {'label': label, 'color': 'blue'})
        add_vertex_with_attrs(LCL_Aux_Graph, {'label': label, 'color': 'blue'})
        add_vertex_with_attrs(CLC_Aux_Graph, {'label': label, 'color': 'blue'})

    # remove stop words in linking phrases (LFs)
    LinkingPhrases = clean_stop_words(LinkingPhrases)

    # add links between concepts and the remaining LFs
    # LF will be red colored
    for lf in LinkingPhrases:
        label = lf['label'].encode('ascii').lower()
        add_vertex_with_attrs(Full_Graph, {'label': label, 'color': 'red'})
        add_vertex_with_attrs(LCL_Aux_Graph, {'label': label, 'color': 'red'})
        add_vertex_with_attrs(CLC_Aux_Graph, {'label': label, 'color': 'red'})

    for c in connections:
        from_id = find_id(Concepts, c['from-id'])
        to_id = find_id(Concepts, c['to-id'])
        if from_id is None:  # from is LinkingF
            # test if the LF was erased because it was a StopWord
            from_id_aux = find_id(LinkingPhrases, c['from-id'])
            if from_id_aux is not None:  # from was not erased because it isnt a stopword
                from_id = from_id_aux + len(Concepts)  # "from ids" are relative to "to ids"
                LCL_Aux_Graph.add_edges([(to_id, from_id)])  # add a link in inverse way
                CLC_Aux_Graph.add_edges([(from_id, to_id)])  # add a link in reverse way
            else:
                continue
        if to_id is None:  # to is LF
            # test if the LF was erased because it was a StopWord
            to_id_aux = find_id(LinkingPhrases, c['to-id'])
            if to_id_aux is not None:
                to_id = to_id_aux + len(Concepts)
                LCL_Aux_Graph.add_edges([(from_id, to_id)])  # add a link in reverse way
                CLC_Aux_Graph.add_edges([(to_id, from_id)])  # add a link in inverse way
            else:  # to was suppressed
                continue
        Full_Graph.add_edges([(from_id, to_id)])

    # create links in the graph with only concepts. ie. replace C1->L->C2 with C1->C2
    # it is usefull to create CCC queries
    for x in Full_Graph.vs():
        if x['color'] == 'blue':
            for suc in Full_Graph.successors(x.index):
                # grafo_LCL.add_edges([(x.index, suc)]) # ???
                for suc2 in Full_Graph.successors(suc):
                    Only_Concepts_Graph.add_edges([(x.index, suc2)])

    # CCC queries
    ccc_qs = []
    for x in Only_Concepts_Graph.vs():
        l1 = x['label']
        # add x to visited
        visited = set()

        visited.add(x.index)
        past = set()
        for suc in Only_Concepts_Graph.successors(x.index):
            if suc not in visited:
                visited.add(suc)
                l2 = Only_Concepts_Graph.vs()[suc]['label']
                l1_and_l2 = remove_repeated(l1, l2)
                for suc2 in Only_Concepts_Graph.successors(suc):
                    if suc2 not in visited:
                        l3 = Only_Concepts_Graph.vs()[suc2]['label']
                        sort_and_add_non_repeated(ccc_qs, l1_and_l2, l3)
                        if len(past) > 0:
                            for p in past:
                                sort_and_add_non_repeated(ccc_qs, l1_and_l2, p)
                        past.add(l2)

    # LCL queries
    lcl_qs = []
    lll_qs = []
    for x in LCL_Aux_Graph.vs():
        sucs = LCL_Aux_Graph.successors(x.index)
        l = len(sucs)
        if l > 1:
            for i in range(l):
                l1 = LCL_Aux_Graph.vs()[sucs[i]]['label']
                for j in range(l):
                    l2 = LCL_Aux_Graph.vs()[sucs[j]]['label']
                    if j > i:
                        sort_and_add_non_repeated(lcl_qs, remove_repeated(x['label'], l1), l2)

            # LLL queries
            if l > 2:
                for i in range(l):
                    l1 = LCL_Aux_Graph.vs()[sucs[i]]['label']
                    for j in range(l):
                        if i >= j:
                            continue  # not process the same combination twice
                        l2 = LCL_Aux_Graph.vs()[sucs[j]]['label']
                        for k in range(l):
                            if k >= j:
                                continue  # not process the same combination twice
                            if i >= k:
                                continue  # not process the same combination twice
                            l3 = LCL_Aux_Graph.vs()[sucs[k]]['label']
                            sort_and_add_non_repeated(lll_qs, remove_repeated(l1, l2), l3)

    # CLC queries
    clc_qs = []
    for x in CLC_Aux_Graph.vs():
        sucs = CLC_Aux_Graph.successors(x.index)
        l = len(sucs)
        if l > 1:
            for i in range(l):
                l1 = CLC_Aux_Graph.vs()[sucs[i]]['label']
                for j in range(l):
                    l2 = CLC_Aux_Graph.vs()[sucs[j]]['label']
                    if j > i:
                        sort_and_add_non_repeated(clc_qs, remove_repeated(x['label'], l1), l2)

    # sys.exit(0)

    f_ccc = open('ccc_' + options.filename + '.txt', 'w')
    f_clc = open('clc_' + options.filename + '.txt', 'w')
    f_lcl = open('lcl_' + options.filename + '.txt', 'w')
    f_lll = open('lll_' + options.filename + '.txt', 'w')

    # print to a file with array to string space-separated conversion
    for a in ccc_qs:
        print>> f_ccc, a
    f_ccc.close()

    for a in clc_qs:
        print>>f_clc, a
    f_clc.close()

    for a in lcl_qs:
        print>>f_lcl, a
    f_lcl.close()

    for a in lll_qs:
        print>>f_lll, a
    f_lll.close()

    # fig=Plot()
    # fig.add(grafo_solo_conceptos, layout="fr")
    # fig.show()
