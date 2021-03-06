import os
import re
import sys
import time
import pickle
import argparse
import numpy as np
from collections import OrderedDict

sys.path.append(os.getcwd())
from tlbo.framework.smbo_offline import SMBO_OFFLINE
from tlbo.facade.notl import NoTL
from tlbo.facade.rgpe import RGPE
from tlbo.facade.obtl_es import ES
from tlbo.facade.obtl import OBTL
from tlbo.facade.random_surrogate import RandomSearch
from tlbo.facade.tst import TST
from tlbo.facade.tstm import TSTM
from tlbo.facade.pogpe import POGPE
from tlbo.facade.stacking_gpr import SGPR
from tlbo.facade.scot import SCoT
from tlbo.facade.mklgp import MKLGP
from tlbo.facade.topo_variant1 import OBTLV
from tlbo.config_space.space_instance import get_configspace_instance

parser = argparse.ArgumentParser()
parser.add_argument('--task_id', type=str, default='main')
parser.add_argument('--exp_id', type=str, default='online')
parser.add_argument('--algo_id', type=str, default='random_forest')
parser.add_argument('--methods', type=str, default='rgpe')
parser.add_argument('--surrogate_type', type=str, default='rf')
parser.add_argument('--test_mode', type=str, default='random')
parser.add_argument('--trial_num', type=int, default=50)
parser.add_argument('--init_num', type=int, default=0)
parser.add_argument('--run_num', type=int, default=-1)
parser.add_argument('--num_source_data', type=int, default=50)
parser.add_argument('--num_source_problem', type=int, default=-1)
parser.add_argument('--num_target_data', type=int, default=10000)
parser.add_argument('--num_random_data', type=int, default=20000)
parser.add_argument('--rep_num', type=int, default=10)
parser.add_argument('--start_id', type=int, default=0)

args = parser.parse_args()
algo_id = args.algo_id
exp_id = args.exp_id
task_id = args.task_id
surrogate_type = args.surrogate_type
n_src_data = args.num_source_data
num_source_problem = args.num_source_problem
n_target_data = args.num_target_data
num_random_data = args.num_random_data
trial_num = args.trial_num
init_num = args.init_num
run_num = args.run_num
test_mode = args.test_mode
rep_num = args.rep_num
start_id = args.start_id
baselines = args.methods.split(',')

data_dir = 'data/hpo_data/'
exp_dir = 'data/exp_results/%s/' % exp_id

if not os.path.exists(exp_dir):
    os.makedirs(exp_dir)

assert test_mode in ['bo', 'random']
if init_num > 0:
    enable_init_design = True
else:
    enable_init_design = False
    # Default number of random configurations.
    init_num = 3

algorithms = ['lightgbm', 'random_forest', 'linear', 'adaboost', 'lda', 'extra_trees']
algo_str = '|'.join(algorithms)
pattern = '(.*)-(%s)-(\d+).pkl' % algo_str


def load_hpo_history():
    source_hpo_ids, source_hpo_data = list(), list()
    random_hpo_data = list()
    for _file in sorted(os.listdir(data_dir)):
        if _file.endswith('.pkl') and _file.find(algo_id) != -1:
            result = re.search(pattern, _file, re.I)
            if result is None:
                continue
            dataset_id, algo_name, total_trial_num = result.group(1), result.group(2), result.group(3)
            if int(total_trial_num) != n_target_data:
                continue
            with open(data_dir + _file, 'rb') as f:
                data = pickle.load(f)
                perfs = np.array(list(data.values()))
            p_max, p_min = np.max(perfs), np.min(perfs)
            if p_max == p_min:
                continue
            if (perfs == perfs[0]).all():
                continue
            if test_mode == 'random':
                _file = data_dir + '%s-%s-random-%d.pkl' % (dataset_id, algo_id, num_random_data)
                if not os.path.exists(_file):
                    continue
            source_hpo_ids.append(dataset_id)
            source_hpo_data.append(data)
    assert len(source_hpo_ids) == len(source_hpo_data)
    print('Load %s source hpo problems for algorithm %s.' % (len(source_hpo_ids), algo_id))

    # Load random hpo data to test the transfer performance.
    if test_mode == 'random':
        for id, hpo_id in enumerate(source_hpo_ids):
            _file = data_dir + '%s-%s-random-%d.pkl' % (hpo_id, algo_id, num_random_data)
            with open(_file, 'rb') as f:
                data = pickle.load(f)
                perfs = np.array(list(data.values()))
                p_max, p_min = np.max(perfs), np.min(perfs)
                if p_max == p_min:
                    print('The same perfs found in the %d-th problem' % id)
                    data = source_hpo_data[id].copy()
                random_hpo_data.append(data)

    print('Load meta-features for each dataset.')
    meta_features = list()
    with open(data_dir + 'dataset_metafeatures.pkl', 'rb') as f:
        dataset_info = pickle.load(f)
        dataset_ids = [item for item in dataset_info['task_ids']]
        dataset_meta_features = list(dataset_info['dataset_embedding'])
        meta_features_dict = dict(zip(dataset_ids, dataset_meta_features))
    for hpo_id in source_hpo_ids:
        assert hpo_id in dataset_ids
        meta_features.append(np.array(meta_features_dict[hpo_id], dtype=np.float64))
    return source_hpo_ids, source_hpo_data, random_hpo_data, meta_features


def fetch_subset(data, num):
    keys, values = list(data.keys())[:num], list(data.values())[:num]
    return OrderedDict(zip(keys, values))


if __name__ == "__main__":
    _hpo_ids, _hpo_data, _random_test_data, _meta_features = load_hpo_history()
    algo_name = 'liblinear_svc' if algo_id == 'linear' else algo_id
    config_space = get_configspace_instance(algo_id=algo_name)
    np.random.seed(42)
    seeds = np.random.randint(low=1, high=10000, size=len(_hpo_ids))
    run_num = len(_hpo_ids) if run_num == -1 else run_num
    num_source_problem = (len(_hpo_ids) - 1) if num_source_problem == -1 else num_source_problem

    idx = np.arange(len(_hpo_data))
    for rep in range(start_id):
        np.random.shuffle(idx)

    for rep in range(start_id, rep_num):
        np.random.shuffle(idx)
        assert len(_hpo_ids) == len(_hpo_data) and len(_hpo_ids) == len(_meta_features)
        hpo_data = [_hpo_data[id] for id in idx]
        hpo_ids = [_hpo_ids[id] for id in idx]
        meta_features = [_meta_features[id] for id in idx]
        if test_mode == 'random':
            random_test_data = [_random_test_data[id] for id in idx]

        for mth in baselines:
            exp_results = list()
            source_hpo_data = list()
            for id in range(run_num):
                print('=' * 20)
                print('[%s-%s] Evaluate %d-th problem - %s.' % (algo_id, mth, id + 1, hpo_ids[id]))
                print('In %d-th problem: %s' % (id, hpo_ids[id]), '#source problem = %d.' % len(source_hpo_data))
                start_time = time.time()

                if id == 0:
                    # The first task.
                    source_hpo_data.append(fetch_subset(hpo_data[id], trial_num))

                # Set target hpo data.
                if test_mode == 'random':
                    target_hpo_data = random_test_data[id]
                else:
                    target_hpo_data = hpo_data[id]

                # Random seed.
                seed = seeds[id]

                if mth == 'rgpe':
                    surrogate_class = RGPE
                elif mth == 'notl':
                    surrogate_class = NoTL
                elif mth == 'es':
                    surrogate_class = ES
                elif mth == 'obtl':
                    surrogate_class = OBTL
                elif mth == 'obtlv':
                    surrogate_class = OBTLV
                elif mth == 'tst':
                    surrogate_class = TST
                elif mth == 'pogpe':
                    surrogate_class = POGPE
                elif mth == 'sgpr':
                    surrogate_class = SGPR
                elif mth == 'scot':
                    surrogate_class = SCoT
                elif mth == 'mklgp':
                    surrogate_class = MKLGP
                elif mth == 'rs':
                    surrogate_class = RandomSearch
                elif mth == 'tstm':
                    surrogate_class = TSTM
                else:
                    raise ValueError('Invalid baseline name - %s.' % mth)
                surrogate = surrogate_class(config_space, source_hpo_data, target_hpo_data, seed,
                                            surrogate_type=surrogate_type,
                                            num_src_hpo_trial=n_src_data)
                smbo = SMBO_OFFLINE(target_hpo_data, config_space, surrogate,
                                    random_seed=seed, max_runs=trial_num,
                                    source_hpo_data=source_hpo_data,
                                    num_src_hpo_trial=n_src_data,
                                    surrogate_type=surrogate_type,
                                    enable_init_design=enable_init_design,
                                    initial_runs=init_num,
                                    acq_func='ei')
                result = list()
                hpo_result = OrderedDict()
                for _ in range(trial_num):
                    config, _, perf, _ = smbo.iterate()
                    # print(config, perf)
                    time_taken = time.time() - start_time
                    adtm, y_inc = smbo.get_adtm(), smbo.get_inc_y()
                    # print('%.3f - %.3f' % (adtm, y_inc))
                    result.append([adtm, y_inc, time_taken])
                    hpo_result[config] = perf
                exp_results.append(result)

                # Add this runhistory to source hpo data.
                source_hpo_data.append(hpo_result)

                print('In %d-th problem: %s' % (id, hpo_ids[id]), 'adtm, y_inc', result[-1])
                print('min/max', smbo.y_min, smbo.y_max)
                print('mean,std', np.mean(smbo.ys), np.std(smbo.ys))
                if hasattr(surrogate, 'hist_ws'):
                    weights = np.array(surrogate.hist_ws)
                    trans = lambda x: ','.join([('%.2f' % item) for item in x])
                    weight_str = '\n'.join([trans(item) for item in weights])
                    print(weight_str)
                    print('Weight stats.')
                    print(trans(np.mean(weights, axis=0)))
                    source_ids = [item[0] for item in enumerate(list(np.mean(weights, axis=0))) if item[1] >= 1e-2]
                    print('Source problems used', source_ids)

            mth_file = '%s_%s_%d_%d_%s_%s_%d.pkl' % (mth, algo_id, n_src_data, trial_num, surrogate_type, task_id, rep)
            with open(exp_dir + mth_file, 'wb') as f:
                data = [np.array(exp_results), np.mean(exp_results, axis=0)]
                pickle.dump(data, f)
