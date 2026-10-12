import {Edge, NodeConfig} from '@core/models/node.model';
import {defaultCaptureIds, downstreamNodes} from './replay-graph';

const node = (id: string, enabled = true) => ({id, name: id, type: 't', category: 'c', enabled, config: {}, x: 0, y: 0}) as NodeConfig;
const edge = (s: string, t: string): Edge => ({source_node: s, source_port: 'out', target_node: t, target_port: 'in'});

//  pb -> a -> b -> sink      other -> a (not downstream of pb)      pb -> off(disabled) -> z
const nodes = ['pb', 'a', 'b', 'sink', 'other', 'off', 'z'].map((id) => node(id, id !== 'off'));
const edges = [edge('pb', 'a'), edge('a', 'b'), edge('b', 'sink'), edge('other', 'a'), edge('pb', 'off'), edge('off', 'z')];

describe('downstreamNodes', () => {
  it('returns the root and everything reachable through enabled nodes', () => {
    expect(downstreamNodes('pb', nodes, edges).map((n) => n.id).sort()).toEqual(['a', 'b', 'pb', 'sink']);
  });

  it('returns nothing for an unknown or disabled root', () => {
    expect(downstreamNodes('nope', nodes, edges)).toEqual([]);
    expect(downstreamNodes('off', nodes, edges)).toEqual([]);
  });
});

describe('defaultCaptureIds', () => {
  it('picks final nodes and the nodes feeding them', () => {
    const sub = downstreamNodes('pb', nodes, edges);
    expect(defaultCaptureIds(sub, edges).sort()).toEqual(['b', 'sink']);
  });

  it('falls back to the single node when there are no edges', () => {
    expect(defaultCaptureIds([node('pb')], [])).toEqual(['pb']);
  });
});
