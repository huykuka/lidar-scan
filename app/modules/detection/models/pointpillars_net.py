"""
Embedded PointPillars network architecture — pure PyTorch, no C++/CUDA extensions.

Adapted from zhulf0804/PointPillars (MIT License) with the following changes:
- Replaced C++ ``hard_voxelize`` with a pure Python/NumPy voxelization
- Replaced CUDA ``nms_cuda`` with a pure PyTorch CPU NMS
- Removed all training-only code (anchor_target, loss, dataset)
- Single-file, zero external dependencies beyond ``torch`` and ``numpy``

Pretrained KITTI weights (``epoch_160.pth``) are directly compatible.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Pure-Python voxelization (replaces C++ hard_voxelize)
# ---------------------------------------------------------------------------

def hard_voxelize_cpu(
    points: np.ndarray,
    voxel_size: list[float],
    point_cloud_range: list[float],
    max_num_points: int = 32,
    max_voxels: int = 40000,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Assign each point to a voxel and collect up to *max_num_points* per voxel.

    Returns:
        voxels:  ``(M, max_num_points, C)``
        coords:  ``(M, 3)`` — voxel indices ``(x, y, z)``
        num_points_per_voxel: ``(M,)``
    """
    pc_range = np.asarray(point_cloud_range, dtype=np.float32)
    vs = np.asarray(voxel_size, dtype=np.float32)

    # Filter to range
    mask = (
        (points[:, 0] >= pc_range[0]) & (points[:, 0] < pc_range[3])
        & (points[:, 1] >= pc_range[1]) & (points[:, 1] < pc_range[4])
        & (points[:, 2] >= pc_range[2]) & (points[:, 2] < pc_range[5])
    )
    points = points[mask]

    if len(points) == 0:
        ndim = 4
        return (
            np.zeros((0, max_num_points, ndim), dtype=np.float32),
            np.zeros((0, 3), dtype=np.int32),
            np.zeros((0,), dtype=np.int32),
        )

    # Compute voxel indices
    coords = np.floor((points[:, :3] - pc_range[:3]) / vs).astype(np.int32)

    grid_size = np.round((pc_range[3:] - pc_range[:3]) / vs).astype(np.int32)
    # Clip to grid bounds
    coords = np.clip(coords, 0, grid_size - 1)

    # Unique voxels — use a flat hash for speed
    flat = coords[:, 0] * (grid_size[1] * grid_size[2]) + coords[:, 1] * grid_size[2] + coords[:, 2]

    # Stable unique preserving first-occurrence order
    _, first_idx, inverse = np.unique(flat, return_index=True, return_inverse=True)
    order = np.argsort(first_idx)
    n_unique = len(first_idx)

    if n_unique > max_voxels:
        n_unique = max_voxels

    ndim = points.shape[1]
    voxels = np.zeros((n_unique, max_num_points, ndim), dtype=np.float32)
    out_coords = np.zeros((n_unique, 3), dtype=np.int32)
    num_points = np.zeros((n_unique,), dtype=np.int32)

    # Map from original unique-id to output slot
    uid_to_slot = np.full(len(first_idx), -1, dtype=np.int32)
    for slot, uid in enumerate(order[:n_unique]):
        uid_to_slot[uid] = slot
        out_coords[slot] = coords[first_idx[uid]]

    for pt_idx in range(len(points)):
        uid = inverse[pt_idx]
        slot = uid_to_slot[uid]
        if slot < 0:
            continue
        cnt = num_points[slot]
        if cnt < max_num_points:
            voxels[slot, cnt] = points[pt_idx, :ndim]
            num_points[slot] = cnt + 1

    return voxels, out_coords, num_points


# ---------------------------------------------------------------------------
# Pure-PyTorch BEV NMS (replaces CUDA nms_gpu)
# ---------------------------------------------------------------------------

def nms_bev_cpu(
    boxes: torch.Tensor,
    scores: torch.Tensor,
    thresh: float,
    pre_maxsize: int | None = None,
    post_max_size: int | None = None,
) -> torch.Tensor:
    """
    Greedy NMS on 2D BEV boxes.

    Args:
        boxes: ``(N, 5)`` — ``[x1, y1, x2, y2, rotation]``.
        scores: ``(N,)``
        thresh: IoU threshold.

    Returns:
        Indices of kept boxes.
    """
    order = scores.argsort(descending=True)
    if pre_maxsize is not None:
        order = order[:pre_maxsize]

    boxes_ordered = boxes[order]
    # Use axis-aligned IoU (ignore rotation for NMS — standard for PointPillars)
    x1 = boxes_ordered[:, 0]
    y1 = boxes_ordered[:, 1]
    x2 = boxes_ordered[:, 2]
    y2 = boxes_ordered[:, 3]
    area = (x2 - x1) * (y2 - y1)

    keep: list[int] = []
    suppressed = torch.zeros(len(order), dtype=torch.bool)

    for i in range(len(order)):
        if suppressed[i]:
            continue
        keep.append(i)

        ix1 = torch.maximum(x1[i], x1[i + 1:])
        iy1 = torch.maximum(y1[i], y1[i + 1:])
        ix2 = torch.minimum(x2[i], x2[i + 1:])
        iy2 = torch.minimum(y2[i], y2[i + 1:])

        inter = torch.clamp(ix2 - ix1, min=0) * torch.clamp(iy2 - iy1, min=0)
        union = area[i] + area[i + 1:] - inter
        iou = torch.where(union > 0, inter / union, torch.zeros_like(inter))

        suppressed[i + 1:] |= iou > thresh

    keep_tensor = order[torch.tensor(keep, dtype=torch.long)]
    if post_max_size is not None:
        keep_tensor = keep_tensor[:post_max_size]
    return keep_tensor


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def limit_period(val: torch.Tensor, offset: float = 0.5, period: float = np.pi) -> torch.Tensor:
    return val - torch.floor(val / period + offset) * period


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

class Anchors:
    def __init__(
        self,
        ranges: list[list[float]],
        sizes: list[list[float]],
        rotations: list[float],
    ) -> None:
        self.ranges = ranges
        self.sizes = sizes
        self.rotations = rotations

    def get_anchors(
        self,
        feature_map_size: torch.Tensor,
        anchor_range: torch.Tensor,
        anchor_size: torch.Tensor,
        rotations: torch.Tensor,
    ) -> torch.Tensor:
        device = feature_map_size.device
        x_centers = torch.linspace(
            anchor_range[0], anchor_range[3], feature_map_size[1] + 1, device=device
        )
        y_centers = torch.linspace(
            anchor_range[1], anchor_range[4], feature_map_size[0] + 1, device=device
        )
        z_centers = torch.linspace(
            anchor_range[2], anchor_range[5], 1 + 1, device=device
        )

        x_shift = (x_centers[1] - x_centers[0]) / 2
        y_shift = (y_centers[1] - y_centers[0]) / 2
        z_shift = (z_centers[1] - z_centers[0]) / 2
        x_centers = x_centers[: feature_map_size[1]] + x_shift
        y_centers = y_centers[: feature_map_size[0]] + y_shift
        z_centers = z_centers[:1] + z_shift

        meshgrids = list(torch.meshgrid(x_centers, y_centers, z_centers, rotations, indexing="ij"))
        for i in range(len(meshgrids)):
            meshgrids[i] = meshgrids[i][..., None]

        anchor_size_expanded = anchor_size[None, None, None, None, :]
        repeat_shape = [feature_map_size[1], feature_map_size[0], 1, len(rotations), 1]
        anchor_size_expanded = anchor_size_expanded.repeat(repeat_shape)
        meshgrids.insert(3, anchor_size_expanded)
        anchors = torch.cat(meshgrids, dim=-1).permute(2, 1, 0, 3, 4).contiguous()
        return anchors.squeeze(0)

    def get_multi_anchors(self, feature_map_size: torch.Tensor) -> torch.Tensor:
        device = feature_map_size.device
        ranges = torch.tensor(self.ranges, device=device)
        sizes = torch.tensor(self.sizes, device=device)
        rotations = torch.tensor(self.rotations, device=device)
        multi_anchors = []
        for i in range(len(ranges)):
            anchors = self.get_anchors(
                feature_map_size=feature_map_size,
                anchor_range=ranges[i],
                anchor_size=sizes[i],
                rotations=rotations,
            )
            multi_anchors.append(anchors[:, :, None, :, :])
        return torch.cat(multi_anchors, dim=2)


def anchors2bboxes(anchors: torch.Tensor, deltas: torch.Tensor) -> torch.Tensor:
    da = torch.sqrt(anchors[:, 3] ** 2 + anchors[:, 4] ** 2)
    x = deltas[:, 0] * da + anchors[:, 0]
    y = deltas[:, 1] * da + anchors[:, 1]
    z = deltas[:, 2] * anchors[:, 5] + anchors[:, 2] + anchors[:, 5] / 2
    w = anchors[:, 3] * torch.exp(deltas[:, 3])
    l = anchors[:, 4] * torch.exp(deltas[:, 4])  # noqa: E741
    h = anchors[:, 5] * torch.exp(deltas[:, 5])
    z = z - h / 2
    theta = anchors[:, 6] + deltas[:, 6]
    return torch.stack([x, y, z, w, l, h, theta], dim=1)


# ---------------------------------------------------------------------------
# Network layers
# ---------------------------------------------------------------------------

class PillarLayer(nn.Module):
    def __init__(
        self,
        voxel_size: list[float],
        point_cloud_range: list[float],
        max_num_points: int,
        max_voxels: tuple[int, int],
    ) -> None:
        super().__init__()
        self.voxel_size = voxel_size
        self.point_cloud_range = point_cloud_range
        self.max_num_points = max_num_points
        self.max_voxels = max_voxels

    @torch.no_grad()
    def forward(self, batched_pts: list[torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        pillars_list, coors_list, npoints_list = [], [], []
        for i, pts in enumerate(batched_pts):
            pts_np = pts.cpu().numpy()
            voxels, coords, num_points = hard_voxelize_cpu(
                pts_np,
                voxel_size=self.voxel_size,
                point_cloud_range=self.point_cloud_range,
                max_num_points=self.max_num_points,
                max_voxels=self.max_voxels[1] if isinstance(self.max_voxels, (list, tuple)) else self.max_voxels,
            )
            device = pts.device
            pillars_list.append(torch.from_numpy(voxels).to(device))
            coors_list.append(torch.from_numpy(coords).long().to(device))
            npoints_list.append(torch.from_numpy(num_points).to(device))

        pillars = torch.cat(pillars_list, dim=0)
        npoints_per_pillar = torch.cat(npoints_list, dim=0)
        coors_batch = []
        for i, cur_coors in enumerate(coors_list):
            coors_batch.append(F.pad(cur_coors, (1, 0), value=i))
        coors_batch = torch.cat(coors_batch, dim=0)
        return pillars, coors_batch, npoints_per_pillar


class PillarEncoder(nn.Module):
    def __init__(
        self,
        voxel_size: list[float],
        point_cloud_range: list[float],
        in_channel: int,
        out_channel: int,
    ) -> None:
        super().__init__()
        self.out_channel = out_channel
        self.vx, self.vy = voxel_size[0], voxel_size[1]
        self.x_offset = voxel_size[0] / 2 + point_cloud_range[0]
        self.y_offset = voxel_size[1] / 2 + point_cloud_range[1]
        self.x_l = int((point_cloud_range[3] - point_cloud_range[0]) / voxel_size[0])
        self.y_l = int((point_cloud_range[4] - point_cloud_range[1]) / voxel_size[1])

        self.conv = nn.Conv1d(in_channel, out_channel, 1, bias=False)
        self.bn = nn.BatchNorm1d(out_channel, eps=1e-3, momentum=0.01)

    def forward(
        self,
        pillars: torch.Tensor,
        coors_batch: torch.Tensor,
        npoints_per_pillar: torch.Tensor,
    ) -> torch.Tensor:
        device = pillars.device

        offset_pt_center = pillars[:, :, :3] - torch.sum(
            pillars[:, :, :3], dim=1, keepdim=True
        ) / npoints_per_pillar[:, None, None]

        x_offset_pi_center = pillars[:, :, :1] - (
            coors_batch[:, None, 1:2] * self.vx + self.x_offset
        )
        y_offset_pi_center = pillars[:, :, 1:2] - (
            coors_batch[:, None, 2:3] * self.vy + self.y_offset
        )

        features = torch.cat(
            [pillars, offset_pt_center, x_offset_pi_center, y_offset_pi_center],
            dim=-1,
        )
        # Consistent with mmdet3d
        features[:, :, 0:1] = x_offset_pi_center
        features[:, :, 1:2] = y_offset_pi_center

        voxel_ids = torch.arange(0, pillars.size(1), device=device)
        mask = voxel_ids[:, None] < npoints_per_pillar[None, :]
        mask = mask.permute(1, 0).contiguous()
        features *= mask[:, :, None]

        features = features.permute(0, 2, 1).contiguous()
        features = F.relu(self.bn(self.conv(features)))
        pooling_features = torch.max(features, dim=-1)[0]

        batched_canvas = []
        bs = coors_batch[-1, 0] + 1
        for i in range(bs):
            cur_coors_idx = coors_batch[:, 0] == i
            cur_coors = coors_batch[cur_coors_idx, :]
            cur_features = pooling_features[cur_coors_idx]

            canvas = torch.zeros(
                (self.x_l, self.y_l, self.out_channel),
                dtype=torch.float32,
                device=device,
            )
            canvas[cur_coors[:, 1], cur_coors[:, 2]] = cur_features
            canvas = canvas.permute(2, 1, 0).contiguous()
            batched_canvas.append(canvas)
        return torch.stack(batched_canvas, dim=0)


class Backbone(nn.Module):
    def __init__(
        self,
        in_channel: int,
        out_channels: list[int],
        layer_nums: list[int],
        layer_strides: list[int] | None = None,
    ) -> None:
        super().__init__()
        if layer_strides is None:
            layer_strides = [2, 2, 2]

        self.multi_blocks = nn.ModuleList()
        for i in range(len(layer_strides)):
            blocks = [
                nn.Conv2d(in_channel, out_channels[i], 3, stride=layer_strides[i], bias=False, padding=1),
                nn.BatchNorm2d(out_channels[i], eps=1e-3, momentum=0.01),
                nn.ReLU(inplace=True),
            ]
            for _ in range(layer_nums[i]):
                blocks.extend([
                    nn.Conv2d(out_channels[i], out_channels[i], 3, bias=False, padding=1),
                    nn.BatchNorm2d(out_channels[i], eps=1e-3, momentum=0.01),
                    nn.ReLU(inplace=True),
                ])
            in_channel = out_channels[i]
            self.multi_blocks.append(nn.Sequential(*blocks))

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")

    def forward(self, x: torch.Tensor) -> list[torch.Tensor]:
        outs = []
        for block in self.multi_blocks:
            x = block(x)
            outs.append(x)
        return outs


class Neck(nn.Module):
    def __init__(
        self,
        in_channels: list[int],
        upsample_strides: list[int],
        out_channels: list[int],
    ) -> None:
        super().__init__()
        self.decoder_blocks = nn.ModuleList()
        for i in range(len(in_channels)):
            decoder_block = nn.Sequential(
                nn.ConvTranspose2d(
                    in_channels[i], out_channels[i], upsample_strides[i],
                    stride=upsample_strides[i], bias=False,
                ),
                nn.BatchNorm2d(out_channels[i], eps=1e-3, momentum=0.01),
                nn.ReLU(inplace=True),
            )
            self.decoder_blocks.append(decoder_block)

        for m in self.modules():
            if isinstance(m, nn.ConvTranspose2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")

    def forward(self, x: list[torch.Tensor]) -> torch.Tensor:
        outs = []
        for i, block in enumerate(self.decoder_blocks):
            outs.append(block(x[i]))
        return torch.cat(outs, dim=1)


class Head(nn.Module):
    def __init__(self, in_channel: int, n_anchors: int, n_classes: int) -> None:
        super().__init__()
        self.conv_cls = nn.Conv2d(in_channel, n_anchors * n_classes, 1)
        self.conv_reg = nn.Conv2d(in_channel, n_anchors * 7, 1)
        self.conv_dir_cls = nn.Conv2d(in_channel, n_anchors * 2, 1)

        conv_layer_id = 0
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.normal_(m.weight, mean=0, std=0.01)
                if conv_layer_id == 0:
                    prior_prob = 0.01
                    bias_init = float(-np.log((1 - prior_prob) / prior_prob))
                    nn.init.constant_(m.bias, bias_init)
                else:
                    nn.init.constant_(m.bias, 0)
                conv_layer_id += 1

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.conv_cls(x), self.conv_reg(x), self.conv_dir_cls(x)


# ---------------------------------------------------------------------------
# Top-level PointPillars network
# ---------------------------------------------------------------------------

class PointPillarsNet(nn.Module):
    """Complete PointPillars network for inference — no CUDA extensions needed."""

    def __init__(
        self,
        nclasses: int = 3,
        voxel_size: list[float] | None = None,
        point_cloud_range: list[float] | None = None,
        max_num_points: int = 32,
        max_voxels: tuple[int, int] = (16000, 40000),
    ) -> None:
        super().__init__()
        if voxel_size is None:
            voxel_size = [0.16, 0.16, 4]
        if point_cloud_range is None:
            point_cloud_range = [0, -39.68, -3, 69.12, 39.68, 1]

        self.nclasses = nclasses
        self.pillar_layer = PillarLayer(
            voxel_size=voxel_size,
            point_cloud_range=point_cloud_range,
            max_num_points=max_num_points,
            max_voxels=max_voxels,
        )
        self.pillar_encoder = PillarEncoder(
            voxel_size=voxel_size,
            point_cloud_range=point_cloud_range,
            in_channel=9,
            out_channel=64,
        )
        self.backbone = Backbone(
            in_channel=64, out_channels=[64, 128, 256], layer_nums=[3, 5, 5]
        )
        self.neck = Neck(
            in_channels=[64, 128, 256],
            upsample_strides=[1, 2, 4],
            out_channels=[128, 128, 128],
        )
        self.head = Head(in_channel=384, n_anchors=2 * nclasses, n_classes=nclasses)

        # KITTI anchor config
        ranges = [
            [0, -39.68, -0.6, 69.12, 39.68, -0.6],
            [0, -39.68, -0.6, 69.12, 39.68, -0.6],
            [0, -39.68, -1.78, 69.12, 39.68, -1.78],
        ]
        sizes = [[0.6, 0.8, 1.73], [0.6, 1.76, 1.73], [1.6, 3.9, 1.56]]
        self.anchors_generator = Anchors(ranges=ranges, sizes=sizes, rotations=[0, 1.57])

        # Inference settings
        self.nms_pre = 100
        self.nms_thr = 0.01
        self.score_thr = 0.1
        self.max_num = 50

    def get_predicted_bboxes_single(
        self,
        bbox_cls_pred: torch.Tensor,
        bbox_pred: torch.Tensor,
        bbox_dir_cls_pred: torch.Tensor,
        anchors: torch.Tensor,
    ) -> dict[str, np.ndarray] | list:
        bbox_cls_pred = bbox_cls_pred.permute(1, 2, 0).reshape(-1, self.nclasses)
        bbox_pred = bbox_pred.permute(1, 2, 0).reshape(-1, 7)
        bbox_dir_cls_pred = bbox_dir_cls_pred.permute(1, 2, 0).reshape(-1, 2)
        anchors = anchors.reshape(-1, 7)

        bbox_cls_pred = torch.sigmoid(bbox_cls_pred)
        bbox_dir_cls_pred = torch.max(bbox_dir_cls_pred, dim=1)[1]

        inds = bbox_cls_pred.max(1)[0].topk(self.nms_pre)[1]
        bbox_cls_pred = bbox_cls_pred[inds]
        bbox_pred = bbox_pred[inds]
        bbox_dir_cls_pred = bbox_dir_cls_pred[inds]
        anchors = anchors[inds]

        bbox_pred = anchors2bboxes(anchors, bbox_pred)

        bbox_pred2d_xy = bbox_pred[:, [0, 1]]
        bbox_pred2d_lw = bbox_pred[:, [3, 4]]
        bbox_pred2d = torch.cat(
            [bbox_pred2d_xy - bbox_pred2d_lw / 2, bbox_pred2d_xy + bbox_pred2d_lw / 2, bbox_pred[:, 6:]],
            dim=-1,
        )

        ret_bboxes, ret_labels, ret_scores = [], [], []
        for i in range(self.nclasses):
            cur_bbox_cls_pred = bbox_cls_pred[:, i]
            score_inds = cur_bbox_cls_pred > self.score_thr
            if score_inds.sum() == 0:
                continue

            cur_bbox_cls_pred = cur_bbox_cls_pred[score_inds]
            cur_bbox_pred2d = bbox_pred2d[score_inds]
            cur_bbox_pred = bbox_pred[score_inds]
            cur_bbox_dir_cls_pred = bbox_dir_cls_pred[score_inds]

            keep_inds = nms_bev_cpu(
                boxes=cur_bbox_pred2d,
                scores=cur_bbox_cls_pred,
                thresh=self.nms_thr,
            )

            cur_bbox_cls_pred = cur_bbox_cls_pred[keep_inds]
            cur_bbox_pred = cur_bbox_pred[keep_inds]
            cur_bbox_dir_cls_pred = cur_bbox_dir_cls_pred[keep_inds]
            cur_bbox_pred[:, -1] = limit_period(
                cur_bbox_pred[:, -1].detach().cpu(), 1, np.pi
            ).to(cur_bbox_pred)
            cur_bbox_pred[:, -1] += (1 - cur_bbox_dir_cls_pred) * np.pi

            ret_bboxes.append(cur_bbox_pred)
            ret_labels.append(torch.zeros_like(cur_bbox_pred[:, 0], dtype=torch.long) + i)
            ret_scores.append(cur_bbox_cls_pred)

        if len(ret_bboxes) == 0:
            return []

        ret_bboxes = torch.cat(ret_bboxes, 0)
        ret_labels = torch.cat(ret_labels, 0)
        ret_scores = torch.cat(ret_scores, 0)
        if ret_bboxes.size(0) > self.max_num:
            final_inds = ret_scores.topk(self.max_num)[1]
            ret_bboxes = ret_bboxes[final_inds]
            ret_labels = ret_labels[final_inds]
            ret_scores = ret_scores[final_inds]

        return {
            "lidar_bboxes": ret_bboxes.detach().cpu().numpy(),
            "labels": ret_labels.detach().cpu().numpy(),
            "scores": ret_scores.detach().cpu().numpy(),
        }

    def forward(
        self,
        batched_pts: list[torch.Tensor],
        mode: str = "test",
    ) -> list[dict[str, np.ndarray] | list]:
        batch_size = len(batched_pts)
        pillars, coors_batch, npoints_per_pillar = self.pillar_layer(batched_pts)
        pillar_features = self.pillar_encoder(pillars, coors_batch, npoints_per_pillar)
        xs = self.backbone(pillar_features)
        x = self.neck(xs)
        bbox_cls_pred, bbox_pred, bbox_dir_cls_pred = self.head(x)

        device = bbox_cls_pred.device
        feature_map_size = torch.tensor(list(bbox_cls_pred.size()[-2:]), device=device)
        anchors = self.anchors_generator.get_multi_anchors(feature_map_size)
        batched_anchors = [anchors for _ in range(batch_size)]

        results = []
        for i in range(batch_size):
            result = self.get_predicted_bboxes_single(
                bbox_cls_pred=bbox_cls_pred[i],
                bbox_pred=bbox_pred[i],
                bbox_dir_cls_pred=bbox_dir_cls_pred[i],
                anchors=batched_anchors[i],
            )
            results.append(result)
        return results
