import os
import argparse
import pickle as pkl
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.lines as mlines
import seaborn as sns

sns.set_style(style='whitegrid')

plt.rc('text', usetex=True)
# plt.rc('font', **{'size': 16, 'family': 'Helvetica'})

plt.rc('font', size=16.0, family='sans-serif')
plt.rcParams['font.sans-serif'] = "Tahoma"

plt.rcParams['figure.figsize'] = (8.0, 4.5)
plt.rcParams['text.latex.preamble'] = [r"\usepackage{amsmath}"]
plt.rcParams["legend.frameon"] = True
plt.rcParams["legend.facecolor"] = 'white'
plt.rcParams["legend.edgecolor"] = 'gray'
plt.rcParams["legend.fontsize"] = 16

# plt.switch_backend('agg')

parser = argparse.ArgumentParser()
parser.add_argument('--benchmark', type=str,
                    default='random_forest')
parser.add_argument('--methods', type=str, default='notl,rgpe,es,rs')
parser.add_argument('--data_dir', type=str, default='./')
parser.add_argument('--transfer_trials', type=int, default=50)
parser.add_argument('--trial_num', type=int, default=20)
parser.add_argument('--plot_type', type=str, choices=['ranking', 'adtm'], default='adtm')
args = parser.parse_args()

benchmark_id = args.benchmark
transfer_trials = args.transfer_trials
run_trials = args.trial_num
plot_type = args.plot_type
methods = args.methods.split(',')
data_dir = args.data_dir


def fetch_color_marker(m_list):
    color_dict = dict()
    marker_dict = dict()
    color_list = ['purple', 'royalblue', 'green', 'brown', 'red', 'orange', 'yellowgreen', 'purple']
    markers = ['s', '^', '*', 'v', 'o', 'p', '2', 'x']

    def fill_values(name, idx):
        color_dict[name] = color_list[idx]
        marker_dict[name] = markers[idx]

    for name in m_list:
        if name.startswith('es'):
            fill_values(name, 0)
        elif name.startswith('notl'):
            fill_values(name, 1)
        elif name.startswith('rgpe'):
            fill_values(name, 2)
        elif name.startswith('rs'):
            fill_values(name, 4)
        elif name.startswith('mbhb') or name.startswith('fabolas'):
            fill_values(name, 3)
        elif name.startswith('Vanilla') or name == 'smac':
            fill_values(name, 5)
        elif name.startswith('random_search'):
            fill_values(name, 6)
        else:
            print(name)
            fill_values(name, 7)
    return color_dict, marker_dict


def smooth(vals, start_idx, end_idx, n_points=4):
    diff = vals[start_idx] - vals[end_idx - 1]
    idxs = np.random.choice(list(range(start_idx, end_idx)), n_points)
    new_vals = vals.copy()
    val_sum = 0.
    new_vals[start_idx:end_idx] = vals[start_idx]
    for idx in sorted(idxs):
        _val = np.random.uniform(0, diff * 0.4, 1)[0]
        diff -= _val
        new_vals[idx:end_idx] -= _val
        val_sum += _val
    new_vals[end_idx - 1] -= (vals[start_idx] - vals[end_idx - 1] - val_sum)
    print(vals[start_idx:end_idx])
    print(new_vals[start_idx:end_idx])
    return new_vals


def create_point(x, stats):
    perf_list = []
    for func in stats:
        timestamp, perf = func
        last_p = 1.0
        for t, p in zip(timestamp, perf):
            if t > x:
                break
            last_p = p
        perf_list.append(last_p)
    return perf_list


def create_plot_points(data, start_time, end_time, point_num=500):
    x = np.linspace(start_time, end_time, num=point_num)
    _mean, _var = list(), list()
    for i, stage in enumerate(x):
        perf_list = create_point(stage, data)
        _mean.append(np.mean(perf_list))
        _var.append(np.std(perf_list))
    # Used to plot errorbar.
    return x, np.array(_mean), np.array(_var)


def get_mean_ranking(adtm_dict, idx, num_ranking):
    ranking_dict = {method: [] for method in adtm_dict.keys()}
    for i in range(num_ranking):
        value_dict = {}
        for method in adtm_dict.keys():
            value_dict[method] = adtm_dict[method][i][idx][0]
        # print(value_dict)
        sorted_item = sorted(value_dict.items(), key=lambda k: k[1])
        cur_rank = 0
        rank_gap = 1
        for _idx, item in enumerate(sorted_item):
            if cur_rank == 0:
                cur_rank += 1
                ranking_dict[item[0]].append(cur_rank)
            else:
                if item[1] == sorted_item[_idx - 1][1]:
                    ranking_dict[item[0]].append(cur_rank)
                    rank_gap += 1
                else:
                    cur_rank += rank_gap
                    rank_gap = 1
                    ranking_dict[item[0]].append(cur_rank)
    ranking_dict = {method: np.mean(ranking_dict[method]) for method in ranking_dict.keys()}
    # print(ranking_dict)
    return ranking_dict


if __name__ == "__main__":
    handles = list()
    fig, ax = plt.subplots()
    lw = 2
    ms = 6
    me = 5

    # Assign the color and marker to each method.

    # color_list = ['royalblue', 'green', 'red', 'orange', 'purple', 'brown', 'yellowgreen', 'purple']
    # markers = ['^', 's', 'v', 'o', '*', 'p', '2', 'x']
    # color_dict, marker_dict = dict(), dict()
    # for i, item in enumerate(sorted(methods)):
    #     color_dict[item] = color_list[i]
    #     marker_dict[item] = markers[i]
    color_dict, marker_dict = fetch_color_marker(methods)
    adtm_dict = {}
    try:
        for idx, method in enumerate(methods):
            filename = "%s_%s_%d_%d.pkl" % (method, benchmark_id, transfer_trials, run_trials)
            path = os.path.join("%sdata/exp_results" % data_dir, filename)
            with open(path, 'rb')as f:
                array = pkl.load(f)
            label_name = r'\textbf{%s}' % (method.upper().replace('_', '-'))
            x = list(range(len(array[1])))
            if plot_type == 'adtm':
                y = array[1][:, 1]
                print(x, y)
                ax.plot(x, y, lw=lw,
                        label=label_name, color=color_dict[method],
                        marker=marker_dict[method], markersize=ms, markevery=me
                        )
                # ax.fill_between(x, y_mean + y_var, y_mean - y_var, alpha=0.1, facecolors=color_dict[method])

                line = mlines.Line2D([], [], color=color_dict[method], marker=marker_dict[method],
                                     markersize=ms, label=label_name)
                handles.append(line)
            elif plot_type == 'ranking':
                adtm_dict[method] = array[0]
                num_ranking = len(array[0])
        if plot_type == 'ranking':
            ranking_dict = {method: [] for method in adtm_dict.keys()}
            for idx in range(len(x)):
                mean_ranking_dict = get_mean_ranking(adtm_dict, idx, num_ranking)
                for method in adtm_dict.keys():
                    ranking_dict[method].append(mean_ranking_dict[method])
            for method in adtm_dict.keys():
                label_name = r'\textbf{%s}' % (method.upper().replace('_', '-'))
                ax.plot(x, ranking_dict[method], lw=lw,
                        label=label_name, color=color_dict[method],
                        marker=marker_dict[method], markersize=ms, markevery=me
                        )
                # ax.fill_between(x, y_mean + y_var, y_mean - y_var, alpha=0.1, facecolors=color_dict[method])

                line = mlines.Line2D([], [], color=color_dict[method], marker=marker_dict[method],
                                     markersize=ms, label=label_name)
                handles.append(line)



    except Exception as e:
        print(e)

    legend = ax.legend(handles=handles, loc=1, ncol=2)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
    ax.set_xlabel('\\textbf{Number of Trials}', fontsize=18)
    if plot_type == 'adtm':
        ax.set_ylabel('\\textbf{ADTM}', fontsize=18)
        plt.subplots_adjust(top=0.97, right=0.968, left=0.11, bottom=0.13)
    elif plot_type == 'ranking':
        ax.set_ylabel('\\textbf{Average Rank}', fontsize=18)
        ax.set_ylim(1, len(methods))
        plt.subplots_adjust(top=0.97, right=0.968, left=0.11, bottom=0.13)

    # # TODO: For each benchmark, the following two settings should be customized.
    # if benchmark_id == 'fcnet':
    #     ax.set_ylim(0.073, .08)
    #     plt.subplots_adjust(top=0.97, right=0.968, left=0.11, bottom=0.13)

    # plt.savefig('%s_%d_%d_%d_result.pdf' % (benchmark_id, runtime_limit, n_worker, rep_num))
    plt.show()