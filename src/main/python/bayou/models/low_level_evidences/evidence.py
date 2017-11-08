# Copyright 2017 Rice University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import tensorflow as tf
import numpy as np
import os
import re
import json
import itertools
from collections import Counter

from bayou.models.low_level_evidences.utils import CONFIG_ENCODER, CONFIG_INFER, C0, UNK


class Evidence(object):

    def init_config(self, evidence, chars_vocab):
        for attr in CONFIG_ENCODER + (CONFIG_INFER if chars_vocab else []):
            self.__setattr__(attr, evidence[attr])

    def dump_config(self):
        js = {attr: self.__getattribute__(attr) for attr in CONFIG_ENCODER + CONFIG_INFER}
        return js

    @staticmethod
    def read_config(js, chars_vocab):
        evidences = []
        for evidence in js:
            name = evidence['name']
            if name == 'apicalls':
                e = APICalls()
            elif name == 'types':
                e = Types()
            elif name == 'keywords':
                e = Keywords()
            else:
                raise TypeError('Invalid evidence name: {}'.format(name))
            e.init_config(evidence, chars_vocab)
            evidences.append(e)
        return evidences

    def read_data_point(self, program):
        raise NotImplementedError('read_data() has not been implemented')

    def set_chars_vocab(self, data):
        raise NotImplementedError('set_chars_vocab() has not been implemented')

    def wrangle(self, data):
        raise NotImplementedError('wrangle() has not been implemented')

    def placeholder(self, config):
        raise NotImplementedError('placeholder() has not been implemented')

    def exists(self, inputs):
        raise NotImplementedError('exists() has not been implemented')

    def init_sigma(self, config):
        raise NotImplementedError('init_sigma() has not been implemented')

    def encode(self, inputs, config):
        raise NotImplementedError('encode() has not been implemented')

    def evidence_loss(self, psi, encoding, config):
        raise NotImplementedError('evidence_loss() has not been implemented')


class APICalls(Evidence):

    def read_data_point(self, program):
        apicalls = program['apicalls'] if 'apicalls' in program else []
        return list(set(apicalls))

    def set_chars_vocab(self, data):
        counts = Counter([c for apicalls in data for c in apicalls])
        self.chars = sorted(counts.keys(), key=lambda w: counts[w], reverse=True)
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)

    def wrangle(self, data):
        wrangled = np.zeros((len(data), 1, self.vocab_size), dtype=np.int32)
        for i, apicalls in enumerate(data):
            for c in apicalls:
                if c in self.vocab:
                    wrangled[i, 0, self.vocab[c]] = 1
        return wrangled

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, 1, self.vocab_size])

    def exists(self, inputs):
        i = tf.reduce_sum(inputs, axis=2)
        return tf.not_equal(tf.count_nonzero(i, axis=1), 0)

    def init_sigma(self, config):
        with tf.variable_scope('apicalls'):
            self.sigma = tf.get_variable('sigma', [])

    def encode(self, inputs, config):
        with tf.variable_scope('apicalls'):
            latent_encoding = tf.zeros([config.batch_size, config.latent_size])
            inp = tf.slice(inputs, [0, 0, 0], [config.batch_size, 1, self.vocab_size])
            inp = tf.reshape(inp, [-1, self.vocab_size])
            encoding = tf.layers.dense(inp, self.units, activation=tf.nn.tanh)
            for i in range(self.num_layers - 1):
                encoding = tf.layers.dense(encoding, self.units, activation=tf.nn.tanh)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding += tf.nn.xw_plus_b(encoding, w, b)
            return latent_encoding

    def evidence_loss(self, psi, encoding, config):
        sigma_sq = tf.square(self.sigma)
        loss = 0.5 * (config.latent_size * tf.log(2 * np.pi * sigma_sq + 1e-10)
                      + tf.square(encoding - psi) / sigma_sq)
        return loss

    @staticmethod
    def from_call(call):
        call = re.sub('^\$.*\$', '', call)  # get rid of predicates
        split = call.split('(')[0].split('.')
        cls, name = split[-2:]
        return [name] if not cls == name else []


class Types(Evidence):

    def read_data_point(self, program):
        types = program['types'] if 'types' in program else []
        return list(set(types))

    def set_chars_vocab(self, data):
        counts = Counter([t for types in data for t in types])
        self.chars = sorted(counts.keys(), key=lambda w: counts[w], reverse=True)
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)

    def wrangle(self, data):
        wrangled = np.zeros((len(data), 1, self.vocab_size), dtype=np.int32)
        for i, types in enumerate(data):
            for t in types:
                if t in self.vocab:
                    wrangled[i, 0, self.vocab[t]] = 1
        return wrangled

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, 1, self.vocab_size])

    def exists(self, inputs):
        i = tf.reduce_sum(inputs, axis=2)
        return tf.not_equal(tf.count_nonzero(i, axis=1), 0)

    def init_sigma(self, config):
        with tf.variable_scope('types'):
            self.sigma = tf.get_variable('sigma', [])

    def encode(self, inputs, config):
        with tf.variable_scope('types'):
            latent_encoding = tf.zeros([config.batch_size, config.latent_size])
            inp = tf.slice(inputs, [0, 0, 0], [config.batch_size, 1, self.vocab_size])
            inp = tf.reshape(inp, [-1, self.vocab_size])
            encoding = tf.layers.dense(inp, self.units, activation=tf.nn.tanh)
            for i in range(self.num_layers - 1):
                encoding = tf.layers.dense(encoding, self.units, activation=tf.nn.tanh)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding += tf.nn.xw_plus_b(encoding, w, b)
            return latent_encoding

    def evidence_loss(self, psi, encoding, config):
        sigma_sq = tf.square(self.sigma)
        loss = 0.5 * (config.latent_size * tf.log(2 * np.pi * sigma_sq + 1e-10)
                      + tf.square(encoding - psi) / sigma_sq)
        return loss

    @staticmethod
    def from_call(call):
        call = re.sub('^\$.*\$', '', call)  # get rid of predicates
        split = list(reversed([q for q in call.split('(')[0].split('.')[:-1] if q[0].isupper()]))
        types = [split[1], split[0]] if len(split) > 1 else [split[0]]
        types = [re.sub('<.*', r'', t) for t in types]  # ignore generic types in evidence

        args = call.split('(')[1].split(')')[0].split(',')
        args = [arg.split('.')[-1] for arg in args]
        args = [re.sub('<.*', r'', arg) for arg in args]  # remove generics
        args = [re.sub('\[\]', r'', arg) for arg in args]  # remove array type
        types_args = [arg for arg in args if not arg == '' and not arg.startswith('Tau_')]

        return types + types_args


class Keywords(Evidence):

    def read_data_point(self, program):
        keywords = program['keywords'] if 'keywords' in program else []
        return list(set(keywords))

    def set_chars_vocab(self, data):
        counts = Counter([c for keywords in data for c in keywords])
        self.chars = sorted(counts.keys(), key=lambda w: counts[w], reverse=True)
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)

    def wrangle(self, data):
        wrangled = np.zeros((len(data), 1, self.vocab_size), dtype=np.int32)
        for i, keywords in enumerate(data):
            for k in keywords:
                if k in self.vocab:
                    wrangled[i, 0, self.vocab[k]] = 1
        return wrangled

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, 1, self.vocab_size])

    def exists(self, inputs):
        i = tf.reduce_sum(inputs, axis=2)
        return tf.not_equal(tf.count_nonzero(i, axis=1), 0)

    def init_sigma(self, config):
        with tf.variable_scope('keywords'):
            self.sigma = tf.get_variable('sigma', [])

    def encode(self, inputs, config):
        with tf.variable_scope('keywords'):
            latent_encoding = tf.zeros([config.batch_size, config.latent_size])
            inp = tf.slice(inputs, [0, 0, 0], [config.batch_size, 1, self.vocab_size])
            inp = tf.reshape(inp, [-1, self.vocab_size])
            encoding = tf.layers.dense(inp, self.units, activation=tf.nn.tanh)
            for i in range(self.num_layers - 1):
                encoding = tf.layers.dense(encoding, self.units, activation=tf.nn.tanh)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding += tf.nn.xw_plus_b(encoding, w, b)
            return latent_encoding

    def evidence_loss(self, psi, encoding, config):
        sigma_sq = tf.square(self.sigma)
        loss = 0.5 * (config.latent_size * tf.log(2 * np.pi * sigma_sq + 1e-10)
                      + tf.square(encoding - psi) / sigma_sq)
        return loss

    @staticmethod
    def split_camel(s):
        s = re.sub('(.)([A-Z][a-z]+)', r'\1#\2', s)  # UC followed by LC
        s = re.sub('([a-z0-9])([A-Z])', r'\1#\2', s)  # LC followed by UC
        return s.split('#')

    @staticmethod
    def from_call(call):
        call = re.sub('^\$.*\$', '', call)  # get rid of predicates
        qualified = call.split('(')[0]
        qualified = re.sub('<.*>', '', qualified).split('.')  # remove generics for keywords
        kws = list(itertools.chain.from_iterable([Keywords.split_camel(s) for s in qualified]))
        return [kw.lower() for kw in kws]


# TODO: handle Javadoc with word2vec
class Javadoc(Evidence):

    def read_data_point(self, program, infer=False):
        javadoc = program['javadoc'] if 'javadoc' in program else None
        if not javadoc:
            javadoc = UNK
        try:  # do not consider non-ASCII javadoc
            javadoc.encode('ascii')
        except UnicodeEncodeError:
            javadoc = UNK
        javadoc = javadoc.split()
        return javadoc

    def set_dicts(self, data):
        if self.pretrained_embed:
            save_dir = os.path.join(self.save_dir, 'embed_' + self.name)
            with open(os.path.join(save_dir, 'config.json')) as f:
                js = json.load(f)
            self.chars = js['chars']
        else:
            self.chars = [C0] + list(set([w for point in data for w in point]))
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)


