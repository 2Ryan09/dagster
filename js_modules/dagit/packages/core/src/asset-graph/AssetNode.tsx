import {gql} from '@apollo/client';
import {Colors, Icon, FontFamily, Box, CaptionMono, Caption, Spinner} from '@dagster-io/ui';
import isEqual from 'lodash/isEqual';
import React from 'react';
import styled from 'styled-components/macro';

import {withMiddleTruncation} from '../app/Util';
import {isAssetLate} from '../assets/CurrentMinutesLateTag';
import {isAssetStale} from '../assets/StaleTag';
import {OpTags} from '../graph/OpTags';
import {TimestampDisplay} from '../schedules/TimestampDisplay';
import {markdownToPlaintext} from '../ui/markdownToPlaintext';

import {AssetLatestRunSpinner, AssetLatestRunWithNotices, AssetRunLink} from './AssetRunLinking';
import {LiveDataForNode} from './Utils';
import {ASSET_NODE_ANNOTATIONS_MAX_WIDTH, ASSET_NODE_NAME_MAX_LENGTH} from './layout';
import {AssetNodeFragment} from './types/AssetNodeFragment';

export const AssetNode: React.FC<{
  definition: AssetNodeFragment;
  liveData?: LiveDataForNode;
  selected: boolean;
  inAssetCatalog?: boolean;
}> = React.memo(({definition, selected, liveData, inAssetCatalog}) => {
  const firstOp = definition.opNames.length ? definition.opNames[0] : null;
  const computeName = definition.graphName || definition.opNames[0] || null;

  // Used for linking to the run with this step highlighted. We only support highlighting
  // a single step, so just use the first one.
  const stepKey = firstOp || '';

  const displayName = definition.assetKey.path[definition.assetKey.path.length - 1];
  const isSource = definition.isSource;

  return (
    <AssetInsetForHoverEffect>
      <AssetNodeContainer $selected={selected}>
        <AssetNodeBox $selected={selected} $isSource={isSource}>
          <Name $isSource={isSource}>
            <span style={{marginTop: 1}}>
              <Icon name={isSource ? 'source_asset' : 'asset'} />
            </span>
            <div style={{overflow: 'hidden', textOverflow: 'ellipsis'}}>
              {withMiddleTruncation(displayName, {
                maxLength: ASSET_NODE_NAME_MAX_LENGTH,
              })}
            </div>
            <div style={{flex: 1}} />
            <Box flex={{alignItems: 'center'}} style={{maxWidth: ASSET_NODE_ANNOTATIONS_MAX_WIDTH}}>
              <AssetLatestRunSpinner liveData={liveData} />
            </Box>
          </Name>
          {definition.description && !inAssetCatalog && (
            <Description>{markdownToPlaintext(definition.description).split('\n')[0]}</Description>
          )}
          {computeName && displayName !== computeName && (
            <Description>
              <Box
                flex={{gap: 4, alignItems: 'flex-end'}}
                style={{marginLeft: -2, overflow: 'hidden'}}
              >
                <Icon name={definition.graphName ? 'job' : 'op'} size={16} />
                <div style={{minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis'}}>
                  {computeName}
                </div>
              </Box>
            </Description>
          )}

          {isSource && !definition.isObservable ? null : (
            <Stats>
              {isSource ? (
                <StatsRow>
                  <span>Observed</span>
                  {liveData?.lastObservation ? (
                    <CaptionMono style={{textAlign: 'right'}}>
                      <AssetRunLink
                        runId={liveData.lastObservation.runId}
                        event={{stepKey, timestamp: liveData.lastObservation.timestamp}}
                      >
                        <TimestampDisplay
                          timestamp={Number(liveData.lastObservation.timestamp) / 1000}
                          timeFormat={{showSeconds: false, showTimezone: false}}
                        />
                      </AssetRunLink>
                    </CaptionMono>
                  ) : (
                    <span>–</span>
                  )}
                </StatsRow>
              ) : (
                <>
                  <StatsRow>
                    <span>Latest&nbsp;Run</span>
                    <Caption style={{textAlign: 'right'}}>
                      <AssetLatestRunWithNotices
                        liveData={liveData}
                        includeFreshness={false}
                        includeRunStatus={false}
                      />
                    </Caption>
                  </StatsRow>
                </>
              )}
            </Stats>
          )}
          <AssetNodeStatusRow definition={definition} liveData={liveData} stepKey={stepKey} />
          {definition.computeKind && (
            <OpTags
              minified={false}
              style={{right: -2, paddingTop: 5}}
              tags={[
                {
                  label: definition.computeKind,
                  onClick: () => {
                    window.requestAnimationFrame(() =>
                      document.dispatchEvent(new Event('show-kind-info')),
                    );
                  },
                },
              ]}
            />
          )}
        </AssetNodeBox>
      </AssetNodeContainer>
    </AssetInsetForHoverEffect>
  );
}, isEqual);

export const AssetNodeStatusRow: React.FC<{
  definition: AssetNodeFragment;
  liveData: LiveDataForNode | undefined;
  stepKey: string;
}> = ({definition, liveData, stepKey}) => {
  if (definition.isSource) {
    return <span />;
  }

  if (!liveData) {
    return (
      <Box
        padding={{horizontal: 8}}
        style={{borderBottomLeftRadius: 4, borderBottomRightRadius: 4, height: 24}}
        flex={{justifyContent: 'space-between', alignItems: 'center'}}
        background={Colors.Gray100}
      >
        <Spinner purpose="caption-text" />
      </Box>
    );
  }

  const {lastMaterialization, runWhichFailedToMaterialize} = liveData;
  const late = isAssetLate(liveData);

  if (runWhichFailedToMaterialize || late) {
    return (
      <Box
        padding={{horizontal: 8}}
        style={{borderBottomLeftRadius: 4, borderBottomRightRadius: 4, height: 24}}
        flex={{justifyContent: 'space-between', alignItems: 'center'}}
        background={Colors.Red50}
      >
        <Caption color={Colors.Red700}>
          {runWhichFailedToMaterialize && late ? `Failed (Late)` : late ? 'Late' : 'Failed'}
        </Caption>
      </Box>
    );
  }

  if (!lastMaterialization) {
    return (
      <Box
        padding={{horizontal: 8}}
        style={{borderBottomLeftRadius: 4, borderBottomRightRadius: 4, height: 24}}
        flex={{justifyContent: 'space-between', alignItems: 'center'}}
        background={Colors.Gray100}
      >
        <Caption color={Colors.Gray700}>Never materialized</Caption>
      </Box>
    );
  }

  if (isAssetStale(liveData)) {
    return (
      <Box
        padding={{horizontal: 8}}
        style={{borderBottomLeftRadius: 4, borderBottomRightRadius: 4, height: 24}}
        flex={{justifyContent: 'space-between', alignItems: 'center'}}
        background={Colors.Yellow50}
      >
        <Caption color={Colors.Yellow700}>Stale</Caption>
      </Box>
    );
  }

  return (
    <Box
      padding={{horizontal: 8}}
      style={{borderBottomLeftRadius: 7, borderBottomRightRadius: 7, height: 24}}
      flex={{justifyContent: 'space-between', alignItems: 'center'}}
      background={Colors.Green50}
    >
      <Caption color={Colors.Green700}>Materialized</Caption>
      <AssetNodeShowOnHover>
        <AssetRunLink
          color={Colors.Green700}
          runId={lastMaterialization.runId}
          event={{stepKey, timestamp: lastMaterialization.timestamp}}
        >
          <TimestampDisplay
            timestamp={Number(lastMaterialization.timestamp) / 1000}
            timeFormat={{showSeconds: false, showTimezone: false}}
          />
        </AssetRunLink>
      </AssetNodeShowOnHover>
    </Box>
  );
};

export const miniColorsForLiveData = (liveData?: LiveDataForNode) => {
  return liveData?.runWhichFailedToMaterialize || isAssetLate(liveData)
    ? {border: Colors.Red500, background: Colors.Red50}
    : !liveData?.lastMaterialization
    ? {border: Colors.Gray500, background: Colors.Gray100}
    : isAssetStale(liveData)
    ? {border: Colors.Yellow500, background: Colors.Yellow50}
    : {border: Colors.Green500, background: Colors.Green50};
};

export const AssetNodeTiny: React.FC<{
  selected: boolean;
  liveData?: LiveDataForNode;
  definition: AssetNodeFragment;
}> = ({selected, liveData, definition}) => {
  const {isSource, assetKey} = definition;
  const {border} = miniColorsForLiveData(liveData);

  return (
    <MinimalAssetNodeBox
      title={assetKey.path[assetKey.path.length - 1]}
      $selected={selected}
      $isSource={isSource}
      $background={border}
      $border={border}
    />
  );
};

export const AssetNodeMinimal: React.FC<{
  selected: boolean;
  definition: AssetNodeFragment;
  liveData?: LiveDataForNode;
}> = ({selected, definition, liveData}) => {
  const {isSource, assetKey} = definition;
  const displayName = assetKey.path[assetKey.path.length - 1];
  const {border, background} = miniColorsForLiveData(liveData);
  return (
    <AssetInsetForHoverEffect>
      <MinimalAssetNodeBox
        $selected={selected}
        $isSource={isSource}
        $background={background}
        $border={border}
      >
        <div style={{position: 'absolute', right: 5, top: 5}}>
          <AssetLatestRunSpinner liveData={liveData} purpose="body-text" />
        </div>

        <MinimalName style={{fontSize: 30}} $isSource={isSource}>
          {withMiddleTruncation(displayName, {maxLength: 17})}
        </MinimalName>
      </MinimalAssetNodeBox>
    </AssetInsetForHoverEffect>
  );
};

export const ASSET_NODE_LIVE_FRAGMENT = gql`
  fragment AssetNodeLiveFragment on AssetNode {
    id
    opNames
    repository {
      id
    }
    assetKey {
      path
    }
    assetMaterializations(limit: 1) {
      timestamp
      runId
    }
    freshnessPolicy {
      maximumLagMinutes
      cronSchedule
    }
    freshnessInfo {
      currentMinutesLate
    }
    assetObservations(limit: 1) {
      timestamp
      runId
    }
    currentLogicalVersion
    projectedLogicalVersion
  }
`;

// Note: This fragment should only contain fields that are needed for
// useAssetGraphData and the Asset DAG. Some pages of Dagit request this
// fragment for every AssetNode on the instance. Add fields with care!
//
export const ASSET_NODE_FRAGMENT = gql`
  fragment AssetNodeFragment on AssetNode {
    id
    graphName
    jobNames
    opNames
    opVersion
    description
    computeKind
    isPartitioned
    isObservable
    isSource
    assetKey {
      path
    }
  }
`;

const AssetInsetForHoverEffect = styled.div`
  padding: 10px 4px 2px 4px;
  height: 100%;
`;

export const AssetNodeContainer = styled.div<{$selected: boolean}>`
  padding: 4px;
`;

const AssetNodeShowOnHover = styled.span`
  display: none;
`;

export const AssetNodeBox = styled.div<{$isSource: boolean; $selected: boolean}>`
  ${(p) =>
    p.$isSource
      ? `border: 2px dashed ${p.$selected ? Colors.Gray600 : Colors.Gray300}`
      : `border: 2px solid ${p.$selected ? Colors.Blue500 : Colors.Blue200}`};

  ${(p) =>
    p.$isSource
      ? `outline: 3px solid ${p.$selected ? Colors.Gray300 : 'transparent'}`
      : `outline: 3px solid ${p.$selected ? Colors.Blue200 : 'transparent'}`};

  background: ${Colors.White};
  border-radius: 8px;
  position: relative;
  &:hover {
    box-shadow: rgba(0, 0, 0, 0.12) 0px 2px 12px 0px;
    ${AssetNodeShowOnHover} {
      display: initial;
    }
  }
`;
const Name = styled.div<{$isSource: boolean}>`
  /** Keep in sync with DISPLAY_NAME_PX_PER_CHAR */
  display: flex;
  padding: 3px 6px;
  background: ${(p) => (p.$isSource ? Colors.Gray100 : Colors.Blue50)};
  font-family: ${FontFamily.monospace};
  border-top-left-radius: 7px;
  border-top-right-radius: 7px;
  font-weight: 600;
  gap: 4px;
`;

const MinimalAssetNodeBox = styled.div<{
  $isSource: boolean;
  $selected: boolean;
  $background: string;
  $border: string;
}>`
  background: ${(p) => p.$background};
  ${(p) =>
    p.$isSource
      ? `border: 4px dashed ${p.$selected ? Colors.Gray500 : p.$border}`
      : `border: 4px solid ${p.$selected ? Colors.Blue500 : p.$border}`};

  ${(p) =>
    p.$isSource
      ? `outline: 8px solid ${p.$selected ? Colors.Gray300 : 'transparent'}`
      : `outline: 8px solid ${p.$selected ? Colors.Blue200 : 'transparent'}`};

  border-radius: 10px;
  position: relative;
  padding: 4px;
  height: 100%;
  min-height: 46px;
  &:hover {
    box-shadow: rgba(0, 0, 0, 0.12) 0px 2px 12px 0px;
  }
`;

const MinimalName = styled(Name)`
  font-weight: 600;
  white-space: nowrap;
  position: absolute;
  background: none;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
`;

const Description = styled.div`
  padding: 4px 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: ${Colors.Gray700};
  border-top: 1px solid ${Colors.Blue50};
  background: ${Colors.White};
  font-size: 12px;
`;

const Stats = styled.div`
  padding: 4px 8px;
  border-top: 1px solid ${Colors.Blue50};
  background: ${Colors.White};
  font-size: 12px;
  line-height: 20px;
`;

const StatsRow = styled.div`
  display: flex;
  justify-content: space-between;
  min-height: 18px;
  & > span {
    color: ${Colors.Gray700};
  }
`;
