"""
    This is a port of the GSS example previously in the main Avalanche repo
    original implementation by https://github.com/gab709.
"""
import torch.nn as nn

from avalanche.benchmarks import Experience
from avalanche.benchmarks.classic import SplitMNIST
from avalanche.benchmarks.generators.benchmark_generators import \
    data_incremental_benchmark
from avalanche.evaluation.metrics import \
    accuracy_metrics, \
    loss_metrics
from avalanche.logging import InteractiveLogger
from avalanche.training.plugins import EvaluationPlugin
from avalanche.training import GSS_greedy
import unittest
import torch
from avalanche.benchmarks.utils import AvalancheSubset
from torch.nn import CrossEntropyLoss
from torch.optim import SGD
from strategies.utils import create_default_args, get_average_metric, get_target_result, set_seed


class GSS(unittest.TestCase):
    """ GSS experiments from the original paper.

    This example the strategy GSS_greedy on Split MNIST.
    The final accuracy is around 77.96% (std 3.5)

    reference: https://arxiv.org/abs/1903.08671
    """

    def test_smnist(self, override_args=None):
        """Split MNIST benchmark"""
        args = create_default_args({
            'cuda': 0, 'lr': 0.05,
            'train_mb_size': 10, 'mem_strength': 10,
            'input_size': [1, 28, 28], 'train_epochs': 3, 'eval_mb_size': 10,
            'mem_size': 300, 'seed': 0}, override_args)

        set_seed(args.seed)
        device = torch.device(f"cuda:{args.cuda}"
                              if torch.cuda.is_available() and
                              args.cuda >= 0 else "cpu")
        model, benchmark = setup_mnist()
        eval_plugin = EvaluationPlugin(
            accuracy_metrics(epoch=True, experience=True, stream=True),
            loss_metrics(stream=True), loggers=[InteractiveLogger()])

        # _____________________________Strategy
        optimizer = SGD(model.parameters(), lr=args.lr)
        strategy = GSS_greedy(model, optimizer, criterion=CrossEntropyLoss(),
                              mem_strength=args.mem_strength,
                              input_size=args.input_size,
                              train_epochs=args.train_epochs,
                              train_mb_size=args.train_mb_size,
                              eval_mb_size=args.eval_mb_size,
                              mem_size=args.mem_size,
                              device=device,
                              evaluator=eval_plugin)

        # ___________________________________________train
        for experience in benchmark.train_stream:
            print(">Experience ", experience.current_experience)
            strategy.train(experience)
            res = strategy.eval(benchmark.test_stream)
        avg_stream_acc = get_average_metric(res)
        print(f"GSS-Split MNIST Average Stream Accuracy: {avg_stream_acc:.2f}")

        target_acc = float(get_target_result('gss', 'smnist'))
        if args.check and target_acc > avg_stream_acc:
            self.assertAlmostEqual(target_acc, avg_stream_acc, delta=0.03)


class FlattenP(nn.Module):
    '''A nn-module to flatten a multi-dimensional tensor to 2-dim tensor.'''

    def forward(self, x):
        batch_size = x.size(0)   # first dimenstion should be batch-dimension.
        return x.view(batch_size, -1)

    def __repr__(self):
        tmpstr = self.__class__.__name__ + '()'
        return tmpstr


class MLP(nn.Module):
    def __init__(self, sizes, bias=True):
        super(MLP, self).__init__()
        layers = []

        for i in range(0, len(sizes) - 1):
            if i < (len(sizes)-2):
                layers.append(nn.Linear(sizes[i], sizes[i + 1]))
                layers.append(nn.ReLU())
            else:
                layers.append(nn.Linear(sizes[i], sizes[i + 1], bias=bias))

        self.net = nn.Sequential(FlattenP(), *layers)

    def forward(self, x):
        return self.net(x)


def shrinking_experience_size_split_strategy(
        experience: Experience):

    experience_size = 1000

    exp_dataset = experience.dataset
    exp_indices = list(range(len(exp_dataset)))

    result_datasets = []

    exp_indices = \
        torch.as_tensor(exp_indices)[
            torch.randperm(len(exp_indices))
        ].tolist()

    result_datasets.append(AvalancheSubset(
        exp_dataset, indices=exp_indices[0:experience_size]))

    return result_datasets


def setup_mnist():

    scenario = data_incremental_benchmark(SplitMNIST(
        n_experiences=5, seed=1), experience_size=0,
        custom_split_strategy=shrinking_experience_size_split_strategy)
    n_inputs = 784
    nh = 100
    nl = 2
    n_outputs = 10
    model = MLP([n_inputs] + [nh] * nl + [n_outputs])

    return model, scenario
