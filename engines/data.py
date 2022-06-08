# -*- coding: utf-8 -*-
# @Author : lishouxian
# @Email : gzlishouxian@gmail.com
# @File : data.py
# @Software: PyCharm
from transformers import BertTokenizerFast
from engines.utils.rematch import rematch
import torch
import numpy as np


class DataManager:
    def __init__(self, configs, logger):
        self.logger = logger
        self.configs = configs
        self.batch_size = configs['batch_size']
        self.max_sequence_length = configs['max_sequence_length']
        self.tokenizer = BertTokenizerFast.from_pretrained('bert-base-chinese')

        self.classes = configs['classes']
        self.num_labels = len(self.classes)
        self.categories = {configs['classes'][index]: index for index in range(0, len(configs['classes']))}
        self.reverse_categories = {class_id: class_name for class_name, class_id in self.categories.items()}

    def padding(self, token):
        if len(token) < self.max_sequence_length:
            token += [0 for _ in range(self.max_sequence_length - len(token))]
        else:
            token = token[:self.max_sequence_length]
        return token

    def prepare_data(self, data):
        text_list = []
        entity_results_list = []
        token_ids_list = []
        segment_ids_list = []
        attention_mask_list = []
        label_vectors = []
        for item in data:
            text = item.get('text')
            entity_results = {}
            token_results = self.tokenizer(text)
            token_ids = self.padding(token_results.get('input_ids'))
            segment_ids = self.padding(token_results.get('token_type_ids'))
            attention_mask = self.padding(token_results.get('attention_mask'))
            label_vector = np.zeros((len(token_ids), len(self.categories), 2))
            for entity in item.get('entities'):
                start_idx = entity['start_idx']
                end_idx = entity['end_idx']
                type_class = entity['type']
                token2char_span_mapping = self.tokenizer(text, return_offsets_mapping=True,
                                                         max_length=self.max_sequence_length,
                                                         truncation=True)['offset_mapping']
                start_mapping = {j[0]: i for i, j in enumerate(token2char_span_mapping) if j != (0, 0)}
                end_mapping = {j[-1] - 1: i for i, j in enumerate(token2char_span_mapping) if j != (0, 0)}
                if start_idx in start_mapping and end_idx in end_mapping:
                    class_id = self.categories[type_class]
                    entity_results.setdefault(class_id, set()).add(entity['entity'])
                    start_in_tokens = start_mapping[start_idx]
                    end_in_tokens = end_mapping[end_idx]
                    label_vector[start_in_tokens, class_id, 0] = 1
                    label_vector[end_in_tokens, class_id, 1] = 1
            text_list.append(text)
            entity_results_list.append(entity_results)
            token_ids_list.append(token_ids)
            segment_ids_list.append(segment_ids)
            attention_mask_list.append(attention_mask)
            label_vectors.append(label_vector)
        token_ids_list = torch.tensor(token_ids_list)
        segment_ids_list = torch.tensor(segment_ids_list)
        attention_mask_list = torch.tensor(attention_mask_list)
        label_vectors = torch.tensor(label_vectors)
        return text_list, entity_results_list, token_ids_list, segment_ids_list, attention_mask_list, label_vectors

    def extract_entities(self, text, model_output):
        """
        从验证集中预测到相关实体
        """
        predict_results = {}
        encode_results = self.tokenizer(text, padding='max_length')
        input_ids = encode_results.get('input_ids')
        token = self.tokenizer.convert_ids_to_tokens(input_ids)
        mapping = rematch(text, token)
        decision_threshold = float(self.configs['decision_threshold'])
        for output in model_output:
            start = np.where(output[:, :, 0] > decision_threshold)
            end = np.where(output[:, :, 1] > decision_threshold)
            for _start, predicate1 in zip(*start):
                for _end, predicate2 in zip(*end):
                    if _start <= _end and predicate1 == predicate2:
                        if len(mapping[_start]) > 0 and len(mapping[_end]) > 0:
                            start_in_text = mapping[_start][0]
                            end_in_text = mapping[_end][-1]
                            entity_text = text[start_in_text: end_in_text + 1]
                            predict_results.setdefault(predicate1, set()).add(entity_text)
                        break
        return predict_results
