import torch
import torch.nn as nn
import torch.nn.functional as F
from collections import OrderedDict
from nets.layers import MixStyle


class _DenseLayer(nn.Sequential):
    def __init__(self, num_input_features, growth_rate, bn_size, drop_rate, **kwargs):
        super(_DenseLayer, self).__init__()
        self.add_module('bn1', nn.BatchNorm2d(num_input_features, affine=False, track_running_stats=False)),
        self.add_module('relu1', nn.ReLU(inplace=True)),
        self.add_module('conv1', nn.Conv2d(num_input_features, bn_size *
                        growth_rate, kernel_size=1, stride=1, bias=False)),
        self.add_module('bn2', nn.BatchNorm2d(bn_size * growth_rate, affine=False, track_running_stats=False)),
        self.add_module('relu2', nn.ReLU(inplace=True)),
        self.add_module('conv2', nn.Conv2d(bn_size * growth_rate, growth_rate,
                        kernel_size=3, stride=1, padding=1, bias=False)),
        self.drop_rate = drop_rate
    
    def forward(self, x):
        new_features = super(_DenseLayer, self).forward(x)
        if self.drop_rate > 0:
            new_features = F.dropout(new_features, p=self.drop_rate, training=self.training)
        return torch.cat([x, new_features], 1)


class _DenseBlock(nn.Sequential):
    def __init__(self, num_layers, num_input_features, bn_size, growth_rate, drop_rate, **kwargs):
        super(_DenseBlock, self).__init__()

        for i in range(num_layers):
            layer = _DenseLayer(num_input_features + i * growth_rate, growth_rate, bn_size, drop_rate)
            self.add_module('denselayer%d' % (i + 1), layer)


class _Transition(nn.Sequential):
    def __init__(self, num_input_features, num_output_features, **kwargs):
        super(_Transition, self).__init__()
        self.add_module('bn', nn.BatchNorm2d(num_input_features, affine=False, track_running_stats=False))
        self.add_module('relu', nn.ReLU(inplace=True))
        self.add_module('conv', nn.Conv2d(num_input_features, num_output_features,
                                          kernel_size=1, stride=1, bias=False))
        self.add_module('pool', nn.AvgPool2d(kernel_size=2, stride=2))


class DenseNet(nn.Module):
    """Densenet-BC model class, based on
    "Densely Connected Convolutional Networks" <https://arxiv.org/pdf/1608.06993.pdf>`_
    Args:
        growth_rate (int) - how many filters to add each layer (`k` in paper)
        block_config (list of 4 ints) - how many layers in each pooling block
        num_init_features (int) - the number of filters to learn in the first convolution layer
        bn_size (int) - multiplicative factor for number of bottle neck layers
          (i.e. bn_size * k features in the bottleneck layer)
        drop_rate (float) - dropout rate after each dense layer
        num_classes (int) - number of classification classes
    """
    def __init__(self, input_shape=[3,96,96], growth_rate=32, block_config=(6, 12, 24, 16),
                 num_init_features=64, bn_size=4, drop_rate=0, num_classes=2, mixstyle=False, **kwargs):

        super(DenseNet, self).__init__()

        # First convolution
        self.features = nn.Sequential(OrderedDict([
            ('conv0', nn.Conv2d(3, num_init_features, kernel_size=7, stride=2, padding=3, bias=False)),
            ('bn0', nn.BatchNorm2d(num_init_features, affine=False, track_running_stats=False)),
            ('relu0', nn.ReLU(inplace=True)),
            ('pool0', nn.MaxPool2d(kernel_size=3, stride=2, padding=1)),
        ]))

        # Each denseblock
        num_features = num_init_features
        for i, num_layers in enumerate(block_config):
            block = _DenseBlock(num_layers=num_layers, num_input_features=num_features,
                                bn_size=bn_size, growth_rate=growth_rate, drop_rate=drop_rate)
            self.features.add_module('denseblock%d' % (i + 1), block)
            if mixstyle and (i in [0, 1]):
                print('Insert MixStyle')
                mixstyle_p, mixstyle_alpha = 0.5, 0.1,
                mixstyle_layer = MixStyle(p=mixstyle_p, alpha=mixstyle_alpha, mix='random')
                self.features.add_module('mixstyle_layer%d' % (i + 1), mixstyle_layer)

            num_features = num_features + num_layers * growth_rate
            if i == 0:
                self.features.add_module('zero_padding', nn.ZeroPad2d(2))
            if i != len(block_config) - 1:
                trans = _Transition(num_input_features=num_features, num_output_features=num_features // 2)
                self.features.add_module('transition%d' % (i + 1), trans)
                num_features = num_features // 2
        self.features.add_module('bn5', nn.BatchNorm2d(num_features, affine=False, track_running_stats=False))
        # Linear layer
        self.classifier = nn.Linear(num_features, num_classes)
        # Official init from torch repo.
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight.data)
            elif isinstance(m, nn.Linear):
                m.bias.data.zero_()

    def forward(self, x):
        features = self.features(x)
        out = F.relu(features,inplace=True)
        out = F.adaptive_avg_pool2d(out, (1,1))
        out = torch.flatten(out, 1)
        out = self.classifier(out)
        return out


class JigsawDenseNet(DenseNet):
    def __init__(self, input_shape=[3,96,96], growth_rate=32, block_config=(6, 12, 24, 16),
                 num_init_features=64, bn_size=4, drop_rate=0, num_classes=2, **kwargs):
        super(JigsawDenseNet, self).__init__(input_shape=input_shape, growth_rate=growth_rate, block_config=block_config,
                                             num_init_features=num_init_features, bn_size=bn_size, drop_rate=drop_rate, num_classes=num_classes, **kwargs)
        self.jig_classifier = nn.Linear(self.classifier.in_features, 31)

    def forward(self, x):
        features = self.features(x)
        out = F.relu(features, inplace=True)
        out = F.adaptive_avg_pool2d(out, (1, 1))
        out = torch.flatten(out, 1)
        return self.classifier(out), self.jig_classifier(out)


class MixStyleDenseNet(DenseNet):
    def __init__(self, input_shape=[3,96,96], mixstyle=True, growth_rate=32, block_config=(6, 12, 24, 16),
                 num_init_features=64, bn_size=4, drop_rate=0, num_classes=2, **kwargs):
        super(MixStyleDenseNet, self).__init__(input_shape=input_shape, growth_rate=growth_rate, block_config=block_config,
                                             num_init_features=num_init_features, bn_size=bn_size, drop_rate=drop_rate, num_classes=num_classes, mixstyle=mixstyle, **kwargs)

        pass

    def forward(self, x, **kwargs):
        features = self.features(x)
        out = F.relu(features, inplace=True)
        out = F.adaptive_avg_pool2d(out, (1, 1))
        out = torch.flatten(out, 1)
        out = self.classifier(out)
        return out

def DenseNet121(args, **kwargs):
    """Constructs a DenseNet-121 model.
    """
    if args.dg_method.lower() == 'jigsaw':
        model = JigsawDenseNet(block_config=(6, 12, 24, 16), **kwargs)
    # elif args.dg_method.lower() == 'mixstyle':
    #     model = MixStyleDenseNet(Bottleneck, [3, 4, 6, 3], mixstyle_layers=['layer1', 'layer2', 'layer3'], **kwargs)
    elif args.dg_method.lower() == 'mixstyle':
        model = MixStyleDenseNet(block_config=(6, 12, 24, 16), mixstyle_layers=[
                               'layer1', 'layer2', 'layer3'], **kwargs)
    else:
        model = DenseNet(block_config=(6, 12, 24, 16), **kwargs)
    return model
