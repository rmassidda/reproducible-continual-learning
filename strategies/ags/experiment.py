import unittest

import torch
from torch.nn import CrossEntropyLoss
from torch.optim import SGD

from avalanche.evaluation.metrics import (
    accuracy_metrics,
    forgetting_metrics,
    loss_metrics
)
from avalanche.training.plugins import EvaluationPlugin
from models import MultiHeadVGGSmall
from strategies.utils import create_default_args, get_average_metric
from strategies.utils import get_target_result
import avalanche as avl


class AGS(unittest.TestCase):
    """
    Reproducing AGS.
    """

    def test_stinyimagenet(self, override_args=None):
        """Split Tiny ImageNet benchmark"""
        args = create_default_args(
            {'cuda': 0, 'lambda_reg': 2., 'alpha': 0.5,
             'verbose': True, 'learning_rate': 0.005,
             'train_mb_size': 200, 'epochs': 70,
             'dataset_root': None}, override_args)

        device = torch.device(f"cuda:{args.cuda}"
                              if torch.cuda.is_available() and
                              args.cuda >= 0 else "cpu")

        """
        "In order to construct a balanced dataset, we assign an equal amount of
        20 randomly chosen classes to each task in a sequence of 10 consecutive
        tasks. This task incremental setting allows using an oracle at test
        time for our evaluation per task, ensuring all tasks are roughly
        similar in terms of difficulty, size, and distribution, making the
        interpretation of the results easier."
        """
        benchmark = avl.benchmarks.SplitTinyImageNet(
            10, return_task_id=True, dataset_root=args.dataset_root)
        model = MultiHeadVGGSmall(n_classes=20)
        criterion = CrossEntropyLoss()

        interactive_logger = avl.logging.InteractiveLogger()

        evaluation_plugin = EvaluationPlugin(
            accuracy_metrics(
                epoch=True, experience=True, stream=True
            ),
            loss_metrics(
                epoch=True, experience=True, stream=True
            ),
            forgetting_metrics(
                experience=True, stream=True
            ),
            loggers=[interactive_logger], benchmark=benchmark)

        cl_strategy = avl.training.AGS(
            model,
            SGD(model.parameters(), lr=args.learning_rate, momentum=0.9),
            criterion, targets=[],
            verbose=args.verbose, train_mb_size=args.train_mb_size,
            train_epochs=args.epochs, eval_mb_size=128, device=device,
            evaluator=evaluation_plugin)

        res = None
        for experience in benchmark.train_stream:
            cl_strategy.train(experience)
            res = cl_strategy.eval(benchmark.test_stream)

        if res is None:
            raise Exception("No results found")

        avg_stream_acc = get_average_metric(res)
        print("AGS-SplitTinyImageNet Average "
              f"Stream Accuracy: {avg_stream_acc:.2f}")

        # Recover target from CSV
        target = get_target_result('ags', 'stiny-imagenet')
        if isinstance(target, list):
            target_acc = target[0]
        else:
            target_acc = target
        target_acc = float(target_acc)

        print(f"The target value was {target_acc:.2f}")

        # Check if the result is close to the target
        if args.check and target_acc > avg_stream_acc:
            self.assertAlmostEqual(target_acc, avg_stream_acc, delta=0.03)
