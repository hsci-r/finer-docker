import os
import re
import hfst
import finnpos

word_id_re = re.compile('\[WORD_ID=.[^\[]*')
uc_re = re.compile(".*([A-Z]|Å|Ä|Ö).*")
digit_re = re.compile(".*[0-9].*")
dash_re = re.compile(".*-.*")

def get_lemma(string):
    lemma_parts = []
    if '[' in string and not string.startswith('['):
        lemma_parts.append(string[:string.index('[')])
    word_id_strs = re.findall(word_id_re, string)
    lemma_parts += [ word_id_str[9:][:-1] for word_id_str in word_id_strs ]
    if ']' in string and not string.endswith(']'):
        lemma_parts.append(string.split(']')[-1].split(':')[0])
    return '#'.join(lemma_parts)

def get_label(string):
    # Remove everything up to the start of the last lemma.
    string = string[string.rfind('[WORD_ID=') + len('[WORD_ID='):]
    
    # Remove the last lemma.
    label = string[string.find(']') + 1:]

    # Add sub label separators.
    label = label.replace('][',']|[')

    sub_labels = label.split('|')

    sub_labels = filter(lambda x: x.find("STYLE=") == -1, sub_labels)
    sub_labels = filter(lambda x: x.find("DRV=") == -1, sub_labels)

    label = '|'.join(sub_labels).lstrip(']|')
    
    return label

def get_lemmas(analyses):
    return [(get_label(a), get_lemma(a)) 
            for a in analyses]

def get_labels(analyses):
    return [get_label(a) for a in analyses]

def filter_ftb_analyses(analyses):
    min_wbs = min(map(lambda x: x.count('[WORD_ID='), analyses))
    return list(filter(lambda x: x.count('[WORD_ID=') == min_wbs, analyses))

def convert(cohorts):
    result = []

    for wordform, cohort in cohorts:
        analyses = []
        for analysis in cohort:

            if wordform == analysis or analysis == wordform + '+?':
                analyses = []
            else:
                analyses.append(analysis)
                
        if len(analyses) == 0:
            result.append('%s\t_\t_\t_\t_' % wordform)
            analyses = []
            continue
        analyses = filter_ftb_analyses(analyses)
        lemmas = get_lemmas(analyses)
        lemma_str = str(lemmas).replace(' ','')
        labels = get_labels(analyses)
        feats = '_'

        if labels != []:
            label_feats = map(lambda x: "OMORFI_FEAT:" + x, labels)
            feats = ' '.join(label_feats)

        label_str = '_' 
                
        if labels != []:
            label_str = ' '.join(labels)
                
        result.append('%s\t%s\t%s\t%s\t%s' % (wordform, feats, '_', label_str, lemma_str))

        analyses = []
        continue
        
    return result

def extract_features(sentences, freq_words):
    # Boundary word.
    BOUNDARY = "_#_"

    # Maximum length of extracted suffix and prefix features.
    MAX_SUF_LEN = 10
    MAX_PRE_LEN = 10

    def get_wf(i, sentence):
        return BOUNDARY if i < 0 or i + 1 > len(sentence) else sentence[i][0]

    def get_suffixes(wf):
        return [ "%u-SUFFIX=%s" % (i, wf[-i:]) 
                 for i in range(1, min(MAX_SUF_LEN + 1, len(wf) + 1)) ]

    def get_prefixes(wf):
        return [ "%u-PREFIX=%s" % (i, wf[:i]) 
                 for i in range(1, min(MAX_PRE_LEN + 1, len(wf) + 1)) ]

    def has_uc(wf):
        return "HAS_UC" if re.match(uc_re, wf) else None

    def has_digit(wf):
        return "HAS_DIGIT" if re.match(digit_re, wf) else None

    def has_dash(wf):
        return "HAS_DASH" if re.match(dash_re, wf) else None

    retval = []
    for sentence in sentences:
        this_labeled_sentence = []
        for i, token in enumerate(sentence):
            try:
                wf, feats, lemma, label, ann = token.split('\t')
            except ValueError:
                continue
            features = []                

            if feats != '_':
                features = feats.split(' ')
        
            if not ann in ['_', '']:
                lemma_list = ann
                if ' ' in ann:
                    lemma_list = ann[:ann.find(' ')]
                
                label_feats = [ "FEAT:" + label for label in 
                                map(lambda x: x[0], eval(lemma_list)) ]

                if len(label_feats) != 0:
                    features += label_feats
                else:
                    features.append("NO_LABELS")

            features.append('PPWORD=' + get_wf(i - 2, sentence))
            features.append('PWORD='  + get_wf(i - 1, sentence))
            features.append('WORD='   + wf)
            features.append('WORD_LEN='   + str(len(wf)))
            features.append('NWORD='  + get_wf(i + 1, sentence))
            features.append('NNWORD=' + get_wf(i + 2, sentence))
            
            features.append('PWORDPAIR='  + get_wf(i - 1, sentence) + "_" + wf)
            features.append('NWORDPAIR='  + wf + "_" + get_wf(i + 1, sentence))
            
            features.append("LC_WORD=" + wf.lower())
            
            if not wf in freq_words:
                features += get_suffixes(wf)
                features += get_prefixes(wf)
            
                features.append(has_uc(wf))
                features.append(has_digit(wf))
                features.append(has_dash(wf))
            
            feat_str = " ".join(filter(None, features))
        
            this_labeled_sentence.append("%s\t%s\t%s\t%s\t%s" % (wf, feat_str, lemma, label, ann))
        retval.append(this_labeled_sentence)
    return retval

def restore_lemmas(labeled_sentence):

    retval = []

    HASH="<HASH>"

    def get_proptags(label_lemma_pairs):
        proptags = set()
        for label, lemma in label_lemma_pairs:
            for part in label.split("|"):
                if part.startswith("[PROP="):
                    proptags.add(part)
        if len(proptags) != 0:
            return ''.join(sorted(proptags))
        return "_"

    def is_subset(tags1, tags2):
        parts1 = tags1.split("|")
        parts2 = tags2.split("|")
        for part in parts1:
            if part not in parts2:
                return False
        return True

    def is_exact_match(tags1, tags2):
        parts1 = tags1.split("|")
        parts2 = tags2.split("|")
        if len(tags1) != len(tags2):
            return False
        for part in parts1:
            if part not in parts2:
                return False
        return True

    for token in labeled_sentence.strip().split('\n'):
        wf, feats, lemma, label, ann = token.split('\t')

        lemmas = ann
        if ann.find(' ') != -1:
            lemmas = ann[:ann.find(' ')]
            ann = ann[ann.find(' ') + 1:]

        ann = "_"
        if lemmas != '_':
            lemmas = eval(lemmas)
            lemma_candidate = None
            
            for this_label, this_lemma in lemmas:
                if is_exact_match(label, this_label):
                    lemma = this_lemma
                    lemma_candidate = None
                    break
                elif lemma_candidate is None and is_subset(label, this_label):
                    lemma_candidate = this_lemma
            if lemma_candidate:
                lemma = lemma_candidate
            elif '[PROPER=PROPER]' in lemmas[0][0]:
                label = lemmas[0][0]
                lemma = lemmas[0][1]
            if '[PROPER=PROPER]' in label:
                ann = get_proptags(lemmas)
        lemma = lemma.replace(HASH, "#")
        retval.append((wf, lemma, label, ann))
    return retval

class TextTagger:
    def __init__(self, datapath = None, tokenizer_file = "omorfi_tokenize.pmatch", lookup_file = None,
                 freq_words_file = "freq_words", model_file = "ftb.omorfi.model"):
        if datapath != None:
            if not os.path.isabs(tokenizer_file):
                tokenizer_file = os.path.join(datapath, tokenizer_file)
                if not os.path.isfile(tokenizer_file):
                    raise FileNotFoundError(tokenizer_file)
            if lookup_file != None and not os.path.isabs(lookup_file):
                lookup_file = os.path.join(datapath, lookup_file)
                if not os.path.isfile(lookup_file):
                    raise FileNotFoundError(lookup_file)
            if not os.path.isabs(freq_words_file):
                freq_words_file = os.path.join(datapath, freq_words_file)
                if not os.path.isfile(freq_words_file):
                    raise FileNotFoundError(freq_words_file)
            if not os.path.isabs(model_file):
                model_file = os.path.join(datapath, model_file)
                if not os.path.isfile(model_file):
                    raise FileNotFoundError(model_file)
        for filename in (tokenizer_file, freq_words_file, model_file):
            if not os.path.isfile(filename):
                raise FileNotFoundError(filename)
        if (lookup_file) != None:
            ls = hfst.HfstInputStream(lookup_file)
            self.lookup = ls.read()
            ls.close()
        else:
            self.lookup = None
        self.tokenizer = hfst.PmatchContainer(tokenizer_file)
        self.freq_words = set(open(freq_words_file).readlines())
        self.tagger = finnpos.Labeler()
        self.tagger.load_model(model_file)

    def __call__(self, text_to_tag):
        retval = []
        sentences = []
        cohorts = []
        if self.lookup != None:
            tokens = text_to_tag.split("\n")
            for token in tokens:
                if token=="":
                    sentences.append(convert(cohorts))
                    cohorts = []
                else:
                    cohort = []
                    outputs = self.lookup.lookup(token)
                    for output in outputs:
                        cohort.append(output[0])
                    cohorts.append((token,cohort))
        else:
            for locations in self.tokenizer.locate(text_to_tag):
                wordform = locations[0].input
                cohort = []
                for location in locations:
                    output = location.output
                    if output != '@_NONMATCHING_@' and ((output != location.input and output != '') or len(locations) == 1):
                        cohort.append(location.output)
                if len(cohort) != 0:
                    cohorts.append((wordform, cohort))
                if locations[0].tag == '<Boundary=Sentence>':
                    sentences.append(convert(cohorts))
                    cohorts = []
        if len(cohorts) != 0:
            sentences.append(convert(cohorts))

        labeled_sentences = []
        for featurized_sentence in extract_features(sentences, self.freq_words):
            this_sentence = []
            for token in restore_lemmas(self.tagger.label('\n'.join(featurized_sentence))):
                this_sentence.append(token)
            retval.append(this_sentence)
        return retval

